"""Desktop adapter for the checked normal-incidence propagation model.

The copied solver differs only in recognizing separate upper/lower Nb indices.
Custom coefficients are relative chi values, never an inferred pm/V calibration.
"""
from functools import lru_cache
from itertools import product
import json
from pathlib import Path

import numpy as np
from .solver import Layer, output_field, response

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'data/baseline_config.json').read_text(encoding='utf-8'))
HISTORY = json.loads((ROOT / 'data/historical_materials.json').read_text(encoding='utf-8'))
AXIS = list(range(20, 201, 5))
SPACERS = CONFIG['hbn_nm']
VERSION = '2026.11.24'
COMPONENTS = ['bbb', 'bcc', 'cbc']
DEFAULT_N = {str(w): {a: complex(*p) for a, p in zip(['b', 'c'], HISTORY['materials']['nb']['nk'][str(w)])}
             for w in (1064, 532)}
DEFAULT_CHI = dict(zip(COMPONENTS, [1+0j, 0j, 0j]))


def complex_text(z):
    return f'{z.real:g}' if z.imag == 0 else f'{z.real:g}{z.imag:+g}i'


def defaults():
    return {'n': {w: {a: complex_text(v) for a, v in row.items()} for w, row in DEFAULT_N.items()},
            'chi': {a: complex_text(v) for a, v in DEFAULT_CHI.items()},
            'upper': AXIS, 'lower': AXIS, 'hbn': SPACERS,
            'reference_intensity': fixed_reference(), 'version': VERSION}


def parse_complex(value, fallback, label, index=False):
    if value is None or isinstance(value, str) and not value.strip():
        return fallback
    try:
        if isinstance(value, bool):
            raise ValueError()
        z = complex(str(value).strip().replace('−', '-').replace('i', 'j').replace('I', 'j'))
    except (ValueError, TypeError):
        raise ValueError(f'{label}：请输入实数或复数，例如 2.01+0.02i。') from None
    if not np.isfinite([z.real, z.imag]).all():
        raise ValueError(f'{label}：数值必须有限。')
    if index and (z.real <= 0 or z.imag < 0):
        raise ValueError(f'{label}：折射率实部应大于 0，吸收部分应不小于 0（n+ik）。')
    return z


def normalize(payload):
    if not isinstance(payload, dict):
        raise ValueError('参数应为一个对象。')
    parameters = {}
    custom = False
    for side, label in [('upper', '上层'), ('lower', '下层')]:
        raw = payload.get(side, {})
        if not isinstance(raw, dict) or not isinstance(raw.get('n', {}), dict) or not isinstance(raw.get('chi', {}), dict):
            raise ValueError(f'{label}材料参数格式错误。')
        n = {}
        for w in ('1064', '532'):
            row = raw.get('n', {}).get(w, {})
            if not isinstance(row, dict):
                raise ValueError(f'{label} {w} nm 折射率格式错误。')
            n[w] = {a: parse_complex(row.get(a), DEFAULT_N[w][a], f'{label} {w} nm {a}轴', True) for a in ('b', 'c')}
        chi = {a: parse_complex(raw.get('chi', {}).get(a), DEFAULT_CHI[a], f'{label} χ{a}') for a in COMPONENTS}
        custom |= any(n[w][a] != DEFAULT_N[w][a] for w in n for a in n[w]) or chi != DEFAULT_CHI
        parameters[side] = {'n': {w: {a: [z.real, z.imag] for a, z in row.items()} for w, row in n.items()},
                            'chi': {a: [z.real, z.imag] for a, z in chi.items()}}
    try:
        angle = float(payload.get('angle', 90))
        linear_angle = float(payload.get('linear_angle', 45))
        h = float(payload.get('h', 50))
        if not np.isfinite([angle, linear_angle, h]).all():
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('角度与厚度必须是有限数值。') from None
    if h not in SPACERS:
        raise ValueError('hBN 厚度须从当前扫描列表中选择。')
    state = payload.get('input', 'Cplus')
    if state not in ('Cplus', 'Cminus', 'linear'):
        raise ValueError('请选择支持的基频光偏振。')
    parameters.update(angle=angle, linear_angle=linear_angle, h=h, input=state, custom_materials=bool(custom))
    return parameters


def optical_values(parameters):
    optical = {name: {int(w): np.array([complex(*v) for v in row])
                      for w, row in HISTORY['materials'][name]['nk'].items()} for name in ('sio2', 'si')}
    for w in (1064, 532):
        optical.setdefault('hbn', {})[w] = np.full(2, np.sqrt(1+3.263*w*w/(w*w-164.4**2)), complex)
    for side in ('upper', 'lower'):
        optical['nb_'+side] = {int(w): np.array([complex(*row[a]) for a in ('b', 'c')])
                              for w, row in parameters[side]['n'].items()}
    return optical


def coefficients(parameters):
    return np.array([[complex(*parameters[s]['chi'][a]) for a in COMPONENTS] for s in ('upper', 'lower')])


def stack(u, h, l, angle):
    return [Layer('nb_upper', u), Layer('hbn', h), Layer('nb_lower', l, angle), Layer('sio2', 285.)]


def input_vector(parameters):
    if parameters['input'] == 'linear':
        angle = np.deg2rad(parameters['linear_angle'])
        return np.array([np.cos(angle), np.sin(angle)], complex)
    return np.array([1, 1j if parameters['input'] == 'Cplus' else -1j])/np.sqrt(2)


@lru_cache(maxsize=1)
def fixed_reference():
    p = normalize({})
    optical = optical_values(p)
    field = output_field(response([Layer('nb_upper', 75.4), Layer('sio2', 285.)], optical,
                                  coefficients(p)[0], 32), np.array([1, 0], complex))
    return float(np.vdot(field, field).real)


def summarize(field):
    ex, ey = field
    return np.array([abs(ex)**2+abs(ey)**2, abs(ex)**2-abs(ey)**2,
                     2*(ex.conjugate()*ey).real, 2*(ex.conjugate()*ey).imag], float)


def solve_point(u, h, l, parameters, optical=None):
    optical = optical if optical is not None else optical_values(parameters)
    field = output_field(response(stack(u, h, l, parameters['angle']), optical, coefficients(parameters), 32), input_vector(parameters))
    return summarize(field)


def clean(values):
    return [float(v) if np.isfinite(v) else None for v in np.asarray(values).ravel()]


def spacer_neighbors(h):
    """Available finite spacer samples. The separate zero-spacer control is excluded."""
    return [value for value in (h-5, h, h+5) if value > 0 and value in SPACERS] if h else []


def solve_plane(h, parameters, optical):
    return np.array([[solve_point(u, h, l, parameters, optical) for l in AXIS] for u in AXIS])


def plane_metrics(planes, h, ref):
    current = planes[h]
    zero = planes[0][..., 0]
    neighborhoods = spacer_neighbors(h)
    keys = sorted(set(neighborhoods + [h]))
    values = np.array([planes[value] for value in keys])
    q = values[..., 0]/ref
    normalized = np.divide(values[..., 1:], values[..., :1], out=np.full_like(values[..., 1:], np.nan),
                           where=q[..., None] > CONFIG['polarization_floor_Q'])
    gain = np.divide(values[..., 0], zero, out=np.full_like(values[..., 0], np.nan),
                     where=zero/ref > CONFIG['gain_denominator_floor_Q'])
    current_index = keys.index(h)
    min_c, min_g, min_q, counts, qualified = [], [], [], [], []
    for ui, li in product(range(len(AXIS)), repeat=2):
        upper = range(max(0, ui-1), min(len(AXIS), ui+2))
        lower = range(max(0, li-1), min(len(AXIS), li+2))
        selection = np.ix_([keys.index(value) for value in neighborhoods], upper, lower)
        circularity = abs(normalized[..., 2][selection])
        ratios = gain[selection]
        intensity = q[selection]
        counts.append(int(intensity.size))
        for target, samples in ((min_c, circularity), (min_g, ratios), (min_q, intensity)):
            target.append(float(samples.min()) if samples.size and np.isfinite(samples).all() else None)
        qualified.append(int(bool(intensity.size) and np.all(circularity >= CONFIG['candidate_min_abs_s3'])
                             and np.all(ratios >= 1) and np.all(intensity >= CONFIG['candidate_min_Q'])))
    return {'Q': clean(q[current_index]), 'G': clean(gain[current_index]),
            **{f'S{j}': clean(current[..., j]) for j in range(4)},
            **{f's{j+1}': clean(normalized[current_index, ..., j]) for j in range(3)},
            'minC': min_c, 'minG': min_g, 'minQ': min_q, 'neighbors': counts, 'qualified': qualified}


def zero_stokes(plane):
    return [clean(plane[..., j]) for j in range(3)]


@lru_cache(maxsize=1)
def baseline_maps():
    return json.loads((ROOT.parent / 'public/data/baseline_maps.json').read_text(encoding='utf-8'))


def baseline_map_sign(parameters):
    input_sign = -1 if parameters['input'] == 'linear' else 1
    angle_sign = 1 if parameters['angle'] == 90 else -1
    return input_sign * angle_sign


def cached_baseline(parameters):
    maps = baseline_maps()
    result = dict(maps)
    if baseline_map_sign(parameters) < 0:
        for name in ('s2', 's3', 'S2', 'S3'):
            result[name] = [-value if value is not None else None for value in maps[name]]
        s0, s1, s2 = maps['zero_stokes']
        result['zero_stokes'] = [s0, s1, [-value for value in s2]]
    return result


@lru_cache(maxsize=4)
def calculate_cached(serialized, include_baseline_maps=True):
    p = json.loads(serialized)
    baseline = not p['custom_materials'] and p['angle'] in (90, -90) and (p['input'] != 'linear' or p['linear_angle'] == 45)
    if baseline:
        maps = cached_baseline(p) if include_baseline_maps else None
    else:
        h = p['h']
        required_h = sorted(set([0, h]+spacer_neighbors(h)))
        optical = optical_values(p)
        planes = {spacer: solve_plane(spacer, p, optical) for spacer in required_h}
        maps = {'upper': AXIS, 'lower': AXIS, 'hbn': [h], 'zero_stokes': zero_stokes(planes[0]),
                **plane_metrics(planes, h, fixed_reference())}
    result = {'maps': maps, 'parameters': p, 'reference_intensity': fixed_reference(),
            'mode': 'baseline' if baseline else 'recalculated',
            'sources': {'Nb': 'historical inputs unless explicitly overridden',
                        'hBN': 'linear-only literature candidate; intrinsic and interface SHG omitted',
                        'substrate': 'SiO2 285 nm / Si, same historical OE inputs',
                        'reference': 'fixed historical 75.4-nm bare Nb, X-linear input; independent of overrides'},
            'experimental_fit': False}
    if baseline and not include_baseline_maps:
        result['baseline_sign'] = baseline_map_sign(p)
    return result


def calculate(payload, *, include_baseline_maps=True):
    parameters = normalize(payload)
    return calculate_cached(json.dumps(parameters, sort_keys=True), include_baseline_maps)
