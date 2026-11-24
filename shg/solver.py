"""Normal-incidence vector SHG from planar anisotropic reciprocal films.

Lengths: nm. exp(-i omega t), n+ik, z into substrate. Fixed laboratory x,y
are Nb b,c for the design scans; Mo angle refers to its metallic a axis.
Undepleted monochromatic pump; only bulk Nb electric-dipole chi(2).
The returned amplitude is E_SH/(chi_bbb_reference * E_inc**2), not counts.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
I2 = np.eye(2, dtype=complex)


@dataclass(frozen=True)
class Layer:
    material: str
    thickness: float
    angle: float = 0.0


def rotation(angle):
    c, s = np.cos(np.deg2rad(angle)), np.sin(np.deg2rad(angle))
    return np.array([[c, -s], [s, c]])


def rotated_diagonal(values, angle):
    q = rotation(angle)
    return (q * np.asarray(values)[..., None, :]) @ q.T


def read_materials():
    data = json.loads((ROOT / 'data/shg_materials.json').read_text(encoding='utf-8'))
    return {name: {int(w): np.array([complex(*n) for n in pair])
                   for w, pair in item['nk'].items()}
            for name, item in data['materials'].items()}


def linear_stack(layers, wavelength, materials):
    """Stable scattering recursion, retaining internal forward/backward waves.

    Internal A is referenced at the layer top, B at its bottom; only decaying
    propagation factors appear. Field maps multiply an incident Jones vector.
    """
    ns = materials['si'][wavelength][0]
    n = [I2] + [rotated_diagonal(materials[l.material][wavelength], l.angle)
                 for l in layers] + [ns * I2]
    p = [I2] + [rotated_diagonal(np.exp(2j*np.pi*materials[l.material][wavelength]
                                      * l.thickness / wavelength), l.angle)
                 for l in layers] + [I2]
    count = len(layers)
    reflection = [None] * (count + 2)
    forward = [None] * (count + 2)
    reflection[-1] = 0 * I2
    for j in range(count, -1, -1):
        rf = np.linalg.solve(n[j]+n[j+1], n[j]-n[j+1])
        rb = -rf
        tf, tb = I2+rf, I2+rb
        load = p[j+1] @ reflection[j+1] @ p[j+1]
        forward[j+1] = np.linalg.solve(I2-rb@load, tf)
        reflection[j] = rf + tb @ load @ forward[j+1]
    a, b = [], []
    incoming = I2
    for j in range(1, count+2):
        top = forward[j] @ incoming
        if j <= count:
            a.append(top)
            b.append(reflection[j] @ p[j] @ top)
        incoming = p[j] @ top
    return reflection[0], incoming, a, b


def field_map(layer, wavelength, materials, a, b, z):
    nk = materials[layer.material][wavelength]
    plus = rotated_diagonal(np.exp(2j*np.pi*np.asarray(z)[..., None]*nk/wavelength), layer.angle)
    minus = rotated_diagonal(np.exp(2j*np.pi*(layer.thickness-np.asarray(z))[..., None]
                                    *nk/wavelength), layer.angle)
    return plus @ a + minus @ b


@lru_cache(maxsize=8)
def quadrature(nodes):
    return np.polynomial.legendre.leggauss(nodes)


def source_basis(layers, materials, nodes=32):
    """Returns response[q,output,input,input] for bbb,bcc,cbc chi components.

    Lorentz reciprocity: E_R,o = i*k_2/2 integral E_test,o(z).P_NL(z) dz.
    Test fields use unit incident air waves at 532 nm. The dot product has
    NO complex conjugation, also in absorbing reciprocal media. There is no
    extra layer-index multiplier: P_NL is physical polarization, not a sheet
    field-jump amplitude normalized independently for each polarization.
    """
    pump = linear_stack(layers, 1064, materials)
    test = linear_stack(layers, 532, materials)
    points, weights = quadrature(nodes)
    contributions = []
    for j, layer in enumerate(layers):
        if layer.material not in ('nb', 'nb_upper', 'nb_lower'):
            continue
        z = (points+1)*layer.thickness/2
        weight = weights*layer.thickness/2
        q = rotation(layer.angle)
        u = q.T @ field_map(layer, 1064, materials, pump[2][j], pump[3][j], z)
        h = q.T @ field_map(layer, 532, materials, test[2][j], test[3][j], z)
        def term(out_axis, a, b):
            return np.einsum('z,zo,zi,zj->oij', weight, h[:, out_axis], u[:, a], u[:, b])
        contributions.append(1j*np.pi/532 * np.array([
            term(0, 0, 0), term(0, 1, 1), term(1, 0, 1)+term(1, 1, 0)]))
    return np.array(contributions)


def response(layers, materials, chi=(1, 0, 0), nodes=32):
    basis = source_basis(layers, materials, nodes)
    if len(basis) == 0:
        return np.zeros((2, 2, 2), complex)
    chi = np.broadcast_to(np.asarray(chi, complex), (len(basis), 3))
    return np.einsum('lq,lqoij->oij', chi, basis)


def output_field(tensor, states):
    return np.einsum('...oij,...i,...j->...o', tensor, states, states)


def stokes(field):
    ex, ey = np.moveaxis(field, -1, 0)
    intensity = abs(ex)**2+abs(ey)**2
    numerator = np.stack([abs(ex)**2-abs(ey)**2, 2*(ex.conj()*ey).real,
                          2*(ex.conj()*ey).imag], axis=-1)
    normalized = np.divide(numerator, intensity[..., None],
                           out=np.full_like(numerator, np.nan),
                           where=intensity[..., None] > 1e-28)
    return intensity, normalized


def structure(d_nb, d_mo, angle, order='Nb/Mo', oxide=285.0):
    nb, mo = Layer('nb', float(d_nb)), Layer('mo', float(d_mo), float(angle))
    pair = [nb, mo] if order == 'Nb/Mo' else [mo, nb]
    if order not in ('Nb/Mo', 'Mo/Nb'):
        raise ValueError('Order must be Nb/Mo or Mo/Nb, from air to substrate.')
    return pair + [Layer('sio2', float(oxide))]


def linear_states(angles):
    angle = np.deg2rad(angles)
    return np.stack([np.cos(angle), np.sin(angle)], axis=-1).astype(complex)


def analyzer_intensity(field, angles, qwp_angle=None):
    """Ideal 532-nm analyzer. QWP matrix diag(1,i); calibrated axis required."""
    if qwp_angle is not None:
        field = rotated_diagonal([1, 1j], qwp_angle) @ field
    return abs(linear_states(angles) @ field)**2
