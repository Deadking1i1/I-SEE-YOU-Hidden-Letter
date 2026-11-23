import math
import random
import struct
import time
import zlib
from pathlib import Path

import pygame


METRICS = {
    "eye_aspect": 2.45,
    "eye_width_fraction": 0.945,
    "eye_height_fraction": 0.69,
    "iris_width_fraction": 0.35,
    "pupil_width_fraction": 0.35,
    "body_rows": 72,
    "iris_rings": 36,
}
BINARY_DIGITS = "01"
FONT_PATH = Path(r"C:\Windows\Fonts\consola.ttf")
LOOP_SECONDS = 18.0
POST_FORMATION_MOTION_SPEED = 1.0
FORMATION_SECONDS = 6.0
LIVE_PRESENT_FPS = 30
CARRIER_FPS = 24.0
CARRIER_START_SECONDS = 0.25
CARRIER_COLUMNS = 112
CARRIER_ROWS = 16
CARRIER_REPEAT = 3
CARRIER_HEADER_BITS = 48
CARRIER_SYNC_BITS = "1010101011001100"
TRANSPORT_MAGIC = b"ISEEVP1"
CARRIER_ROW_GEOMETRY = (
    (-0.75, -0.5833333, 0.5166667),
    (-0.70, -0.6333333, 0.5500000),
    (-0.65, -0.6666667, 0.5833333),
    (-0.60, -0.7166667, 0.6166667),
    (-0.55, -0.7500000, 0.6500000),
    (-0.50, -0.7666667, 0.6833333),
    (-0.45, -0.8000000, 0.7000000),
    (-0.40, -0.8500000, 0.7666667),
    (0.40, -0.8166667, 0.6666667),
    (0.45, -0.8000000, 0.6333333),
    (0.50, -0.7666667, 0.6000000),
    (0.55, -0.7333333, 0.5500000),
    (0.60, -0.6833333, 0.5166667),
    (0.65, -0.6333333, 0.4666667),
    (0.70, -0.5833333, 0.4000000),
    (0.75, -0.5166667, 0.3333333),
)
SQUINT_START_DELAY = 5.0
SQUINT_CYCLE_SECONDS = 18.0
SQUINT_ACTIVE_SECONDS = 11.0
SQUINT_RAMP_SECONDS = 2.5
SQUINT_MAX = 0.34
LID_LUT_STEPS = 512
DEFAULT_RENDER_PROFILE = {
    "body_density": 1.0,
    "body_font_scale": 1.0,
    "body_alpha": 1.0,
    "contour_font_scale": 1.0,
    "iris_font_scale": 1.0,
    "iris_density": 1.0,
    "iris_spacing": 2.65,
    "iris_brightness": 1.0,
    "iris_highlight": 1.0,
}

CARRIER_DATA_BITS = CARRIER_ROWS * CARRIER_COLUMNS - CARRIER_HEADER_BITS
VISUAL_CARRIER_BLOCKS = 184
VISUAL_CARRIER_SEED = 0x49534559
_visual_carrier_rng = random.Random(VISUAL_CARRIER_SEED)
VISUAL_CARRIER_BITS = "".join(
    _visual_carrier_rng.choice(BINARY_DIGITS)
    for _ in range(VISUAL_CARRIER_BLOCKS * CARRIER_DATA_BITS)
)
ENCRYPTED_PAYLOAD_PATH = Path(__file__).with_name("hidden_message_payload.bin")
MAX_CARRIER_PAYLOAD_BYTES = 1_048_576


def _hamming_encode_bits(bits):
    data_positions = (3, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15)
    encoded = []
    for start in range(0, len(bits), len(data_positions)):
        chunk = bits[start:start + len(data_positions)].ljust(len(data_positions), "0")
        code = [0] * 16
        for position, bit in zip(data_positions, chunk):
            code[position] = int(bit)
        for parity in (1, 2, 4, 8):
            code[parity] = sum(code[position] for position in range(1, 16) if position & parity and position != parity) % 2
        encoded.extend(str(code[position]) for position in range(1, 16))
    return "".join(encoded)


def _load_encrypted_carrier_bits():
    try:
        if ENCRYPTED_PAYLOAD_PATH.stat().st_size > MAX_CARRIER_PAYLOAD_BYTES:
            return ""  # shortcut: oversized legacy payloads are skipped; regenerate the compact payload to embed it.
        encrypted_payload = ENCRYPTED_PAYLOAD_PATH.read_bytes()
    except OSError:
        return ""
    transport = (
        TRANSPORT_MAGIC
        + struct.pack(">I", len(encrypted_payload))
        + encrypted_payload
        + struct.pack(">I", zlib.crc32(encrypted_payload) & 0xffffffff)
    )
    return "".join(bit * CARRIER_REPEAT for bit in _hamming_encode_bits("".join(f"{byte:08b}" for byte in transport)))


ENCRYPTED_CARRIER_BITS = _load_encrypted_carrier_bits()
CARRIER_TOTAL_BLOCKS = max(
    VISUAL_CARRIER_BLOCKS,
    (len(ENCRYPTED_CARRIER_BITS) + CARRIER_DATA_BITS - 1) // CARRIER_DATA_BITS,
)
CARRIER_BITS = (ENCRYPTED_CARRIER_BITS or VISUAL_CARRIER_BITS).ljust(CARRIER_TOTAL_BLOCKS * CARRIER_DATA_BITS, "0")

UPPER_LID_CURVES = (
    ((0.000, 0.500), (0.040, 0.350), (0.120, 0.100), (0.420, 0.000)),
    ((0.420, 0.000), (0.510, -0.015), (0.600, -0.010), (0.650, 0.010)),
    ((0.650, 0.010), (0.720, 0.035), (0.880, 0.290), (1.000, 0.470)),
)
LOWER_LID_CURVES = (
    ((0.000, 0.500), (0.040, 0.650), (0.140, 0.860), (0.400, 0.970)),
    ((0.400, 0.970), (0.510, 0.990), (0.620, 0.950), (0.700, 0.850)),
    ((0.700, 0.850), (0.820, 0.760), (0.920, 0.560), (1.000, 0.470)),
)


def smoothstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def loop_zoom(t):
    # The desktop presentation uses a locked full-eye camera; character motion carries the loop.
    return 0.0


def gaze_offset(motion_time):
    """Return a restrained, smooth normalized iris gaze offset."""
    return (
        0.052 * math.sin(motion_time * 0.34) + 0.018 * math.sin(motion_time * 0.71 + 1.4),
        0.030 * math.sin(motion_time * 0.27 + 0.8) + 0.010 * math.sin(motion_time * 0.59),
    )


def blink_amount(t):
    """Return a deterministic occasional blink amount in [0, 1]."""
    if t < FORMATION_SECONDS:
        return 0.0
    cycle = (t - FORMATION_SECONDS - 2.0) % 8.5
    if cycle < 0.16:
        return smoothstep(cycle / 0.16)
    if cycle < 0.24:
        return 1.0
    if cycle < 0.44:
        return 1.0 - smoothstep((cycle - 0.24) / 0.20)
    return 0.0


def squint_amount(t):
    start = FORMATION_SECONDS + SQUINT_START_DELAY
    if t < start:
        return 0.0
    cycle = (t - start) % SQUINT_CYCLE_SECONDS
    if cycle < SQUINT_RAMP_SECONDS:
        return SQUINT_MAX * smoothstep(cycle / SQUINT_RAMP_SECONDS)
    release_start = SQUINT_ACTIVE_SECONDS - SQUINT_RAMP_SECONDS
    if cycle < release_start:
        return SQUINT_MAX
    if cycle < SQUINT_ACTIVE_SECONDS:
        return SQUINT_MAX * (1.0 - smoothstep((cycle - release_start) / SQUINT_RAMP_SECONDS))
    return 0.0


def squint_sweep(t):
    start = FORMATION_SECONDS + SQUINT_START_DELAY
    if t < start:
        return 0.0
    cycle = (t - start) % SQUINT_CYCLE_SECONDS
    if cycle >= SQUINT_ACTIVE_SECONDS:
        return 0.0
    phase = smoothstep(cycle / SQUINT_ACTIVE_SECONDS)
    return -0.075 + 0.15 * phase


def carrier_frame_index(t):
    return max(0, int(round((float(t) - CARRIER_START_SECONDS) * CARRIER_FPS)))


def carrier_frame_bits(frame_index):
    block = frame_index % CARRIER_TOTAL_BLOCKS
    start = block * CARRIER_DATA_BITS
    data = CARRIER_BITS[start:start + CARRIER_DATA_BITS].ljust(CARRIER_DATA_BITS, "0")
    header = CARRIER_SYNC_BITS + f"{block:016b}" + f"{CARRIER_TOTAL_BLOCKS:016b}"
    return header + data


def carrier_x_positions(left, right):
    return [left + (right - left) * (index + 0.5) / CARRIER_COLUMNS for index in range(CARRIER_COLUMNS)]


def with_alpha(color, factor):
    return (*color[:3], max(0, min(255, int(color[3] * factor))))


def cubic_point(points, t):
    u = 1.0 - t
    p0, p1, p2, p3 = points
    return (
        u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
        u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1],
    )


def sample_cubic_arc(points, count):
    """Return approximately arc-length-spaced samples on one cubic segment."""
    lut = [(0.0, cubic_point(points, 0.0))]
    for index in range(1, 65):
        t = index / 64.0
        previous = lut[-1][1]
        current = cubic_point(points, t)
        distance = math.hypot(current[0] - previous[0], current[1] - previous[1])
        lut.append((lut[-1][0] + distance, current))
    total = lut[-1][0]
    result = []
    for index in range(max(2, count)):
        target = total * index / max(1, count - 1)
        for cursor in range(1, len(lut)):
            if lut[cursor][0] >= target:
                before_distance, before = lut[cursor - 1]
                after_distance, after = lut[cursor]
                blend = (target - before_distance) / max(1e-9, after_distance - before_distance)
                result.append((before[0] + (after[0] - before[0]) * blend, before[1] + (after[1] - before[1]) * blend))
                break
    return result


def _evaluate_lid(curves, x):
    x = max(0.0, min(1.0, x))
    for segment in curves:
        start = segment[0][0]
        end = segment[-1][0]
        if x <= end:
            # Invert the cubic x(t) rather than assuming x varies linearly in t.
            lo, hi = 0.0, 1.0
            for _ in range(28):
                mid = (lo + hi) * 0.5
                if cubic_point(segment, mid)[0] < x:
                    lo = mid
                else:
                    hi = mid
            return cubic_point(segment, (lo + hi) * 0.5)[1]
    return curves[-1][-1][1]


def upper_lid_y(x):
    if x <= 0.0:
        return 0.500
    if x >= 1.0:
        return 0.470
    return _evaluate_lid(UPPER_LID_CURVES, x)


def lower_lid_y(x):
    if x <= 0.0:
        return 0.500
    if x >= 1.0:
        return 0.470
    return _evaluate_lid(LOWER_LID_CURVES, x)


def inside_eye(x, y):
    return upper_lid_y(x) <= y <= lower_lid_y(x)


class AnimationClock:
    def __init__(self, speed=1.0):
        self.speed = speed
        self.elapsed = 0.0
        self.paused = False
        self._last = None

    def reset(self, now=0.0):
        self.elapsed = 0.0
        self._last = now

    def set_paused(self, paused, now):
        self.paused = paused
        self._last = now

    def tick(self, now):
        if self._last is None:
            self._last = now
        if not self.paused:
            self.elapsed += max(0.0, now - self._last) * self.speed
        self._last = now
        return self.elapsed


class Eye:
    def __init__(self, seed=7, detail=1.0, profile=None):
        self.rng = random.Random(seed)
        self.detail = detail
        self.profile = {**DEFAULT_RENDER_PROFILE, **(profile or {})}
        self.font_cache = {}
        self.rotated_cache = {}
        self.row_bounds_cache = {}
        self.iris_layout_cache = {}
        self._layer = None
        self._canvas = None
        self._present_cache = None
        self._present_key = None
        self._glyph_scale = 1.0
        self._blink = 0.0
        self._squint = 0.0
        self._lid_lut = tuple(
            (index / LID_LUT_STEPS, upper_lid_y(index / LID_LUT_STEPS), lower_lid_y(index / LID_LUT_STEPS))
            for index in range(LID_LUT_STEPS + 1)
        )

    def _font(self, size):
        size = max(4, int(size))
        if size not in self.font_cache:
            self.font_cache[size] = (pygame.font.Font(str(FONT_PATH), size)
                                     if FONT_PATH.exists() else pygame.font.SysFont("dejavusansmono", size))
        return self.font_cache[size]

    def _digit(self, digit, size, color):
        color = self._cache_color(color)
        key = (digit, int(size), color)
        if key not in self.font_cache:
            self.font_cache[key] = self._font(size).render(digit, True, color)
        return self.font_cache[key]

    @staticmethod
    def _cache_color(color):
        # Animation alpha does not need 256 unique rasterized glyph variants.
        return (*color[:3], max(0, min(255, int(color[3] / 8) * 8)))

    def _rotated_digit(self, digit, size, color, angle):
        color = self._cache_color(color)
        angle = round(angle / 3.0) * 3.0
        key = (digit, int(size), color, angle)
        if key not in self.rotated_cache:
            self.rotated_cache[key] = pygame.transform.rotate(self._digit(digit, size, color), angle)
        return self.rotated_cache[key]

    def _rotated_text(self, text, size, color, angle):
        color = self._cache_color(color)
        angle = round(angle / 3.0) * 3.0
        key = (text, int(size), color, angle)
        if key not in self.rotated_cache:
            glyph = self._font(size).render(text, True, color)
            self.rotated_cache[key] = pygame.transform.rotate(glyph, angle)
        return self.rotated_cache[key]

    def _eye_dimensions(self, width, height):
        eye_width = min(width * METRICS["eye_width_fraction"], height * METRICS["eye_height_fraction"] * METRICS["eye_aspect"])
        return eye_width, eye_width / METRICS["eye_aspect"]

    @staticmethod
    def _half_width(y):
        edge = max(0.0, 1.0 - abs(y) ** 1.42)
        lid_weight = 1.035 if y < 0 else 0.955
        irregularity = 1.0 + 0.022 * math.sin(y * 9.0) + 0.014 * math.sin(y * 23.0)
        return 0.5 * edge ** 0.62 * lid_weight * irregularity

    def _lid_bounds(self, x):
        u = max(0.0, min(1.0, (x + 1.0) * 0.5))
        position = u * LID_LUT_STEPS
        index = min(LID_LUT_STEPS - 1, int(position))
        blend = position - index
        _, upper_a, lower_a = self._lid_lut[index]
        _, upper_b, lower_b = self._lid_lut[index + 1]
        upper = upper_a + (upper_b - upper_a) * blend
        lower = lower_a + (lower_b - lower_a) * blend
        if self._squint:
            midpoint = (upper + lower) * 0.5
            upper += (midpoint - upper) * self._squint
            lower += (midpoint - lower) * self._squint
        if self._blink:
            upper += (lower - upper) * self._blink
        return 2.0 * upper - 1.0, 2.0 * lower - 1.0

    def _inside_render_eye(self, u, v):
        upper, lower = self._lid_bounds(u * 2.0 - 1.0)
        normalized_v = v * 2.0 - 1.0
        return upper <= normalized_v <= lower

    def _row_bounds(self, y):
        samples = 120
        valid = []
        for index in range(samples + 1):
            x = -1.0 + 2.0 * index / samples
            upper, lower = self._lid_bounds(x)
            if upper <= y <= lower:
                valid.append(x)
        if not valid:
            return None
        return max(-1.0, min(valid)), min(1.0, max(valid))

    def _glyph_fits_eye(self, cx, cy, eye_width, eye_height, rect):
        x0, y0, x1, y1 = rect
        for px, py in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            u = 0.5 + (px - cx) / max(1.0, eye_width)
            v = 0.5 + (py - cy) / max(1.0, eye_height)
            upper, lower = self._lid_bounds(u * 2.0 - 1.0)
            if not (upper <= v * 2.0 - 1.0 <= lower):
                return False
        return True

    def _band_color(self, row, column, total_rows):
        if row % 13 == 0 or (column % 43 == 0 and abs(row - total_rows / 2) < total_rows * 0.34):
            return (245, 250, 255, 255)
        if row % 11 == 0:
            return (72, 181, 229, 215)
        return (148, 192, 218, 205)

    @staticmethod
    def _edge_fade(u):
        left = smoothstep(max(0.0, min(1.0, u / 0.18)))
        right = 1.0 - smoothstep(max(0.0, min(1.0, (u - 0.82) / 0.18)))
        return 0.28 + 0.72 * left * right

    def _body_depth_factor(self, x, cx, eye_width, y):
        u = 0.5 + (x - cx) / max(1.0, eye_width)
        edge = self._edge_fade(u)
        left_key = 1.0 - max(0.0, min(1.0, (u - 0.50) / 0.50))
        side_light = 0.68 + 0.32 * left_key
        vertical = 0.92 + 0.08 * (1.0 - min(1.0, abs(y)))
        return edge * side_light * vertical

    def _draw_carrier(self, layer, cx, cy, eye_width, eye_height, t, animate):
        bits = carrier_frame_bits(carrier_frame_index(t) if animate else 0)
        font_size = max(7, int(12 * self._glyph_scale))
        color = (235, 246, 250, 245)
        for row, (y_norm, left, right) in enumerate(CARRIER_ROW_GEOMETRY):
            y = cy + y_norm * eye_height * 0.5
            for column, x_norm in enumerate(carrier_x_positions(left, right)):
                glyph = self._digit(bits[row * CARRIER_COLUMNS + column], font_size, color)
                x = cx + x_norm * eye_width * 0.5
                cell_width = eye_width * 0.5 * (right - left) / CARRIER_COLUMNS
                pygame.draw.rect(
                    layer,
                    (0, 0, 0, 180),
                    (int(x - cell_width * 0.62), int(y - glyph.get_height() * 0.58), max(1, int(cell_width * 1.24)), glyph.get_height() + 2),
                )
                layer.blit(glyph, (int(x - glyph.get_width() * 0.5), int(y - glyph.get_height() * 0.5)))

    def _draw_contours(self, layer, cx, cy, eye_width, eye_height, detail, visibility):
        contour_base = 18 if detail >= 0.9 else 12
        font_size = max(int(8 * self._glyph_scale), int(contour_base * detail * self.profile["contour_font_scale"] * self._glyph_scale))
        contour_layers = (
            (0.0, 5, (255, 255, 255, 255)),
        )
        for offset, text_length, contour_color in contour_layers:
            for curves, base_color in ((UPPER_LID_CURVES, contour_color), (LOWER_LID_CURVES, with_alpha(contour_color, 0.96))):
                for segment_index, segment in enumerate(curves):
                    samples = sample_cubic_arc(segment, max(60, int(120 * detail)))
                    for index, (px, py) in enumerate(samples[:-1]):
                        qx, qy = samples[index + 1]
                        angle = math.degrees(math.atan2(qy - py, qx - px))
                        x = cx + eye_width * (px - 0.5)
                        y = cy + eye_height * (py - 0.5 + offset)
                        tangent = math.radians(angle)
                        nx, ny = -math.sin(tangent), math.cos(tangent)
                        if curves is UPPER_LID_CURVES and ny < 0:
                            nx, ny = -nx, -ny
                        if curves is LOWER_LID_CURVES and ny > 0:
                            nx, ny = -nx, -ny
                        corner_factor = min(
                            1.0,
                            max(0.0, px / 0.22),
                            max(0.0, (1.0 - px) / 0.22),
                        )
                        contour_size = max(int(5 * self._glyph_scale), int(font_size * (0.30 + 0.30 * corner_factor)))
                        inset = contour_size * 0.50
                        accent = offset == 0.0 and (segment_index * 19 + index * 7) % 17 in (0, 1, 2)
                        color = (255, 255, 255, 255) if accent else base_color
                        color = with_alpha(color, visibility * (0.78 + 0.22 * self._edge_fade(px)))
                        local_length = 1 if corner_factor < 0.36 else text_length
                        text = "".join(BINARY_DIGITS[(segment_index * 13 + index * 5 + i) % 2] for i in range(local_length))
                        glyph = self._rotated_text(text, contour_size, color, angle)
                        for extra_inset in (0.0, 0.55, 1.10, 1.70, 2.40):
                            contour_x = x + nx * (inset + extra_inset * contour_size)
                            contour_y = y + ny * (inset + extra_inset * contour_size)
                            left = contour_x - glyph.get_width() * 0.5
                            top = contour_y - glyph.get_height() * 0.5
                            rect = (left, top, left + glyph.get_width(), top + glyph.get_height())
                            if self._glyph_fits_eye(cx, cy, eye_width, eye_height, rect):
                                layer.blit(glyph, (int(left), int(top)))
                                break
            terminal_size = max(int(8 * self._glyph_scale), int(font_size * 0.72))
            terminal_color = with_alpha((245, 250, 252, 255), visibility)
            terminal_specs = (
                (0.000, 0.500, "0101"),
                (0.078, upper_lid_y(0.078) + 0.045, "01"),
                (0.078, lower_lid_y(0.078) - 0.045, "10"),
            )
            for u, v, text in terminal_specs:
                glyph = self._rotated_text(text, terminal_size, terminal_color, 0.0)
                x = cx + eye_width * (u - 0.5)
                y = cy + eye_height * (v - 0.5)
                left = x - glyph.get_width() * 0.5
                top = y - glyph.get_height() * 0.5
                if self._glyph_fits_eye(cx, cy, eye_width, eye_height, (left, top, left + glyph.get_width(), top + glyph.get_height())):
                    layer.blit(glyph, (int(left), int(top)))

    def _draw_body(self, layer, cx, cy, eye_width, eye_height, zoom, detail, motion_time=0.0, visibility=1.0, formation=1.0, exclude_iris=True, iris_cx=None, iris_cy=None, underlay=False):
        rows = max(24, int(METRICS["body_rows"] * (1.50 if underlay else 1.0) * detail * self.profile["body_density"]))
        base_size = 8 if underlay else (16 if detail >= 0.9 else 8)
        font_size = max(int(8 * self._glyph_scale), int(base_size * self.profile["body_font_scale"] * (1.0 + zoom * 0.18) * self._glyph_scale))
        iris_rx = eye_width * METRICS["iris_width_fraction"] * 0.5
        iris_ry = iris_rx * 0.98
        iris_cx = cx if iris_cx is None else iris_cx
        iris_cy = cy if iris_cy is None else iris_cy
        curve_samples = [index / 64.0 for index in range(65)]
        y_min = min(2.0 * upper_lid_y(x) - 1.0 for x in curve_samples)
        y_max = max(2.0 * lower_lid_y(x) - 1.0 for x in curve_samples)
        for row in range(rows):
            y = y_min + (row + 0.5) * (y_max - y_min) / rows
            cache_key = (rows, row)
            bounds = self.row_bounds_cache.get(cache_key)
            if bounds is None:
                bounds = self._row_bounds(y)
                self.row_bounds_cache[cache_key] = bounds
            if bounds is None:
                continue
            left = cx + bounds[0] * eye_width * 0.5
            right = cx + bounds[1] * eye_width * 0.5
            flow_y = 0.010 * math.sin(motion_time * 0.55 + row * 0.19)
            flow_x = 0.004 * math.sin(motion_time * 0.38 + row * 0.27)
            baseline = cy + (y + 0.012 * math.sin(row * 0.83) + flow_y) * eye_height * 0.5
            x = left + (row % 3) * 1.2 * self._glyph_scale + flow_x * eye_width
            column = 0
            while x < right:
                target_x = x
                nx = (x - iris_cx) / max(1.0, iris_rx)
                ny = (baseline - iris_cy) / max(1.0, iris_ry)
                gap_period = 29 if underlay else 23
                gap_slots = (27,) if underlay else (20, 21)
                gap = (column + row * 3) % gap_period in gap_slots
                if (not exclude_iris or nx * nx + ny * ny > 1.0) and not gap:
                    if formation < 1.0:
                        source_x = cx + math.sin(row * 1.73 + column * 2.17) * eye_width * 0.55
                        x = source_x + (target_x - source_x) * formation
                    stream_u = (x - cx) / max(1.0, eye_width * 0.5)
                    stream_curve = 0.085 * stream_u * stream_u * (1.0 - min(1.0, abs(y) * 0.45))
                    if y > 0.0:
                        stream_curve *= -1.0
                    glyph_baseline = baseline + stream_curve * eye_height * 0.5
                    digit = BINARY_DIGITS[(row * 17 + column * 7) % 2]
                    center_u = 0.5 + (x + font_size * 0.25 - cx) / max(1.0, eye_width)
                    corner_factor = min(
                        1.0,
                        max(0.0, (center_u - 0.035) / 0.24),
                        max(0.0, (0.965 - center_u) / 0.24),
                    )
                    glyph_size = max(8, int(font_size * (0.62 + 0.38 * corner_factor)))
                    pulse = 0.94 + 0.06 * math.sin(motion_time * 0.7 + row * 0.21 + column * 0.05)
                    lid_weight = 1.06 if row < rows * 0.22 else (0.86 if row > rows * 0.80 else 0.94)
                    depth_factor = self._body_depth_factor(x, cx, eye_width, y)
                    band = (32, 92, 158, 68) if underlay else self._band_color(row, column, rows)
                    glyph = self._digit(digit, glyph_size, with_alpha(band, visibility * pulse * lid_weight * depth_factor * self.profile["body_alpha"] * (0.42 + 0.58 * corner_factor)))
                    top = glyph_baseline - glyph.get_height() * 0.55
                    terminal_gap = corner_factor < 0.32 and (row + column) % 3 in (1, 2)
                    if not terminal_gap and self._glyph_fits_eye(cx, cy, eye_width, eye_height, (x, top, x + glyph.get_width(), top + glyph.get_height())):
                        layer.blit(glyph, (int(x), int(top)))
                x = target_x + font_size * (0.88 + 0.12 * ((row * 5 + column) % 4) / 3.0)
                column += 1

    def _draw_iris(self, layer, cx, cy, iris_rx, iris_ry, eye_width, eye_height, zoom, detail, motion_time=0.0, visibility=1.0, formation=1.0, eye_cx=None, eye_cy=None):
        eye_cx = cx if eye_cx is None else eye_cx
        eye_cy = cy if eye_cy is None else eye_cy
        rings = max(18, int(METRICS["iris_rings"] * detail))
        iris_base = 12 if detail >= 0.9 else 8
        font_size = max(int(8 * self._glyph_scale), int(iris_base * self.profile["iris_font_scale"] * (1.0 + zoom * 0.24) * self._glyph_scale))
        layout_key = (round(iris_rx, 3), round(iris_ry, 3), rings, font_size, round(detail, 3))
        layouts = self.iris_layout_cache.get(layout_key)
        if layouts is None:
            layouts = []
            for ring in range(rings):
                radius = 0.36 + 0.62 * ring / max(1, rings - 1)
                rx = iris_rx * radius
                ry = iris_ry * radius
                circumference = math.tau * math.sqrt((rx * rx + ry * ry) * 0.5)
                density = (0.94 + 0.08 * math.sin(ring * 0.71) + 0.04 * math.sin(ring * 2.31 + 0.6)) * self.profile["iris_density"]
                spacing = self.profile["iris_spacing"]
                count = max(16, int(circumference / (font_size * spacing) * density))
                arc_lut = [(0.0, 0.0)]
                for sample in range(1, 129):
                    previous_angle = math.tau * (sample - 1) / 128.0
                    angle_sample = math.tau * sample / 128.0
                    px = rx * math.cos(previous_angle)
                    py = ry * math.sin(previous_angle)
                    qx = rx * math.cos(angle_sample)
                    qy = ry * math.sin(angle_sample)
                    arc_lut.append((arc_lut[-1][0] + math.hypot(qx - px, qy - py), angle_sample))
                total_arc = arc_lut[-1][0]
                phase_arc = total_arc * (0.018 + 0.012 * math.sin(ring * 1.37 + 0.2))
                segments = []
                for segment in range(count):
                    if (segment + ring * 5) % 19 == 18:
                        continue
                    target_arc = (total_arc * segment / count + phase_arc) % total_arc
                    for cursor in range(1, len(arc_lut)):
                        if arc_lut[cursor][0] >= target_arc:
                            before_distance, before_angle = arc_lut[cursor - 1]
                            after_distance, after_angle = arc_lut[cursor]
                            blend = (target_arc - before_distance) / max(1e-9, after_distance - before_distance)
                            angle = before_angle + (after_angle - before_angle) * blend
                            break
                    irregular = 1.0 + (0.035 - radius * 0.012) * math.sin(segment * 2.7 + ring * 0.9)
                    segments.append((segment, angle, irregular))
                direction = -1.0 if ring % 5 in (0, 1) else 1.0
                angular_speed = direction * (0.0035 + 0.00022 * ring)
                layouts.append((ring, radius, rx, ry, angular_speed, tuple(segments)))
            self.iris_layout_cache[layout_key] = tuple(layouts)

        for ring, radius, rx, ry, angular_speed, segments in layouts:
            for segment, base_angle, irregular in segments:
                angle = base_angle
                angle += motion_time * angular_speed
                target_x = cx + math.cos(angle) * rx * irregular
                target_y = cy + math.sin(angle) * ry * irregular
                u = (target_x - (eye_cx - eye_width * 0.5)) / eye_width
                v = (target_y - (eye_cy - eye_height * 0.5)) / eye_height
                if not self._inside_render_eye(u, v):
                    continue
                source_angle = angle + 0.8 * math.sin(ring * 1.7 + segment * 0.31)
                source_radius = 1.12 + 0.12 * math.sin(segment * 0.7 + ring)
                source_x = cx + math.cos(source_angle) * iris_rx * source_radius
                source_y = cy + math.sin(source_angle) * iris_ry * source_radius
                x = source_x + (target_x - source_x) * formation
                y = source_y + (target_y - source_y) * formation
                if ring % 9 == 0:
                    color = (255, 255, 255, 255) if segment % 3 else (132, 232, 249, 255)
                elif ring % 5 == 0:
                    color = (22, 214, 242, 250)
                elif ring % 7 == 0:
                    color = (125, 96, 215, 235)
                elif ring % 3 == 0:
                    color = (42, 178, 241, 250)
                elif ring % 2 == 0:
                    color = (34, 140, 226, 245)
                else:
                    color = (16, 76, 163, 225)
                upper_left = max(0.0, math.cos(angle + 2.35)) ** 5
                lower_right = max(0.0, math.cos(angle - 0.65)) ** 9
                highlight = min(1.0, max(upper_left * (1.0 - radius * 0.45), lower_right * (0.55 + radius * 0.45)) * self.profile["iris_highlight"])
                inner_upper_left = upper_left * max(0.0, 1.0 - max(0.0, radius - 0.42) / 0.42)
                if inner_upper_left > 0.28 and ring % 3 in (0, 1):
                    color = (255, 255, 255, 255) if ring < rings * 0.70 else (84, 221, 241, 245)
                elif highlight > 0.52 and ring % 4 in (0, 1):
                    color = (238, 247, 250, 250) if ring < rings * 0.55 else (64, 218, 241, 245)
                side_light = 0.58 + 0.42 * max(0.0, math.cos(angle - 2.55))
                brightness = (0.90 + 0.10 * math.sin(motion_time * 0.72 + ring * 0.51 + segment * 0.17)) * (0.82 + 0.30 * highlight) * side_light * self.profile["iris_brightness"]
                color = with_alpha(color, visibility * brightness)
                segment_length = 3 + ((ring + segment) % 3 if detail >= 0.9 else (ring + segment) % 2)
                text = "".join(BINARY_DIGITS[(ring * 11 + segment * 5 + i) % 2] for i in range(segment_length))
                tangent = -math.degrees(angle) + 90.0
                glyph = self._rotated_text(text, font_size, color, tangent)
                layer.blit(glyph, (int(x - glyph.get_width() / 2), int(y - glyph.get_height() / 2)))

        # Keep radial detail subordinate to the ring structure.
        spoke_count = max(6, int(8 * detail))
        for spoke in range(spoke_count):
            angle = math.tau * spoke / spoke_count + 0.025 * math.sin(spoke * 2.1)
            start = 0.42 + 0.06 * math.sin(spoke * 1.9)
            length = 0.22 + 0.04 * math.sin(spoke * 0.73 + 1.0)
            steps = 2
            for step in range(steps):
                radius = start + length * step / max(1, steps - 1)
                x = cx + math.cos(angle) * iris_rx * radius
                y = cy + math.sin(angle) * iris_ry * radius
                color = (30, 112, 190, 105) if step % 3 else (128, 197, 224, 135)
                color = with_alpha(color, visibility)
                digit = BINARY_DIGITS[(spoke + step) % 2]
                glyph = self._rotated_digit(digit, max(int(8 * self._glyph_scale), font_size - int(self._glyph_scale)), color, -math.degrees(angle))
                layer.blit(glyph, (int(x - glyph.get_width() / 2), int(y - glyph.get_height() / 2)))

    def _draw_pupil(self, layer, cx, cy, pupil_rx, pupil_ry):
        points = []
        for index in range(96):
            angle = math.tau * index / 96
            irregularity = 1.0 + 0.014 * math.sin(angle * 3.0 + 0.4) + 0.008 * math.sin(angle * 7.0 - 0.7)
            points.append((cx + math.cos(angle) * pupil_rx * irregularity, cy + math.sin(angle) * pupil_ry * irregularity))
        pygame.draw.polygon(layer, (0, 0, 0, 255), points)

    def _draw_blink_mask(self, layer, cx, cy, eye_width, eye_height):
        if max(self._blink, self._squint) <= 0.0:
            return
        samples = 96
        upper = [(cx - eye_width * 0.5 + eye_width * index / samples, cy) for index in range(samples + 1)]
        lower = list(reversed(upper))
        for index in range(samples + 1):
            x = -1.0 + 2.0 * index / samples
            upper_y, lower_y = self._lid_bounds(x)
            upper[index] = (upper[index][0], cy + eye_height * upper_y * 0.5)
            lower[samples - index] = (lower[samples - index][0], cy + eye_height * lower_y * 0.5)
        top = [(0, 0), (layer.get_width(), 0)] + list(reversed(upper))
        bottom = [(0, layer.get_height()), (layer.get_width(), layer.get_height())] + lower
        pygame.draw.polygon(layer, (0, 0, 0, 255), top)
        pygame.draw.polygon(layer, (0, 0, 0, 255), bottom)

    def draw(self, screen, t, zoom, detail=1.0, animate=False, draw_iris=True, render_scale=2):
        output = screen
        out_w, out_h = output.get_size()
        scale = max(0.25, float(render_scale))
        width, height = max(1, int(out_w * scale)), max(1, int(out_h * scale))
        self._glyph_scale = scale
        present_key = None
        if animate:
            present_key = (
                out_w,
                out_h,
                int(float(t) * LIVE_PRESENT_FPS),
                round(float(zoom), 5),
                round(float(detail), 3),
                round(scale, 3),
                bool(draw_iris),
            )
            if self._present_key == present_key and self._present_cache is not None:
                output.blit(self._present_cache, (0, 0))
                return
        else:
            self._present_key = None
        if self._layer is None or self._layer.get_size() != (width, height):
            self._layer = pygame.Surface((width, height), pygame.SRCALPHA)
        layer = self._layer
        layer.fill((0, 0, 0, 0))
        cx = width * 0.5 + zoom * width * 0.025
        cy = height * 0.52
        eye_width, eye_height = self._eye_dimensions(width, height)
        camera = 1.0 + zoom * 0.9
        eye_width *= camera
        eye_height *= camera
        iris_cx = cx + eye_width * 0.03
        iris_cy = cy
        if animate:
            formation_seconds = FORMATION_SECONDS
            phase = min(1.0, max(0.0, t / formation_seconds))
            fade_in = smoothstep(min(1.0, phase / 0.18))
            body_visibility = 0.08 + 0.92 * fade_in
            iris_visibility = smoothstep(max(0.0, (phase - 0.24) / 0.24))
            body_formation = smoothstep(min(1.0, phase / 0.70))
            iris_formation = smoothstep(max(0.0, min(1.0, (phase - 0.28) / 0.48)))
            motion_time = min(float(t), formation_seconds)
            if t > formation_seconds:
                motion_time += (float(t) - formation_seconds) * POST_FORMATION_MOTION_SPEED
        else:
            body_visibility = 1.0
            iris_visibility = 1.0
            body_formation = 1.0
            iris_formation = 1.0
            motion_time = 0.0
        self._blink = blink_amount(float(t)) if animate else 0.0
        self._squint = squint_amount(float(t)) if animate else 0.0
        if animate and t >= FORMATION_SECONDS:
            gaze_x, gaze_y = gaze_offset(motion_time)
            gaze_x += squint_sweep(float(t))
            iris_cx += gaze_x * eye_width
            iris_cy += gaze_y * eye_height
        if detail >= 0.9:
            self._draw_body(layer, cx, cy, eye_width, eye_height, zoom, detail, motion_time, body_visibility, body_formation, exclude_iris=draw_iris, iris_cx=iris_cx, iris_cy=iris_cy, underlay=True)
        self._draw_body(layer, cx, cy, eye_width, eye_height, zoom, detail, motion_time, body_visibility, body_formation, exclude_iris=draw_iris, iris_cx=iris_cx, iris_cy=iris_cy)
        self._draw_contours(layer, cx, cy, eye_width, eye_height, detail, body_visibility)
        self._draw_carrier(layer, cx, cy, eye_width, eye_height, t, animate)
        iris_rx = eye_width * METRICS["iris_width_fraction"] * 0.5
        iris_ry = iris_rx * 0.98
        if draw_iris:
            limbal_rx = iris_rx * 1.035
            pygame.draw.ellipse(layer, (0, 0, 0, 255), (iris_cx - limbal_rx, iris_cy - limbal_rx * 0.98, limbal_rx * 2, limbal_rx * 1.96))
            self._draw_iris(layer, iris_cx, iris_cy, iris_rx, iris_ry, eye_width, eye_height, zoom, detail, motion_time, iris_visibility, iris_formation, eye_cx=cx, eye_cy=cy)
            # iris_rx is already a radius, so the configured width ratio maps directly to pupil radius.
            pupil_rx = iris_rx * METRICS["pupil_width_fraction"]
            pupil_ry = pupil_rx * 0.98
            self._draw_pupil(layer, iris_cx, iris_cy, pupil_rx, pupil_ry)
        self._draw_carrier(layer, cx, cy, eye_width, eye_height, t, animate)
        self._draw_blink_mask(layer, cx, cy, eye_width, eye_height)
        if scale == 1.0:
            output.fill((0, 0, 0))
            output.blit(layer, (0, 0))
        else:
            if self._canvas is None or self._canvas.get_size() != (width, height):
                self._canvas = pygame.Surface((width, height), pygame.SRCALPHA)
            self._canvas.fill((0, 0, 0, 255))
            self._canvas.blit(layer, (0, 0))
            output.blit(pygame.transform.smoothscale(self._canvas, (out_w, out_h)), (0, 0))
        if present_key is not None:
            self._present_cache = output.copy()
            self._present_key = present_key


def render_frame(t, size=(960, 540), detail=1.0, animate=False, draw_iris=True, profile=None, render_scale=2):
    pygame.init()
    screen = pygame.Surface(size)
    Eye(profile=profile).draw(screen, t, loop_zoom(t), detail, animate=animate, draw_iris=draw_iris, render_scale=render_scale)
    pygame.quit()
    return screen


def save_screenshot(screen, directory="output/screenshots"):
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"eye_{int(time.time())}.png"
    pygame.image.save(screen, path)
    return path


def main():
    pygame.init()
    screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
    pygame.display.set_caption("Binary Eye")
    clock = pygame.time.Clock()
    eye = Eye()
    animation_clock = AnimationClock()
    animation_clock.reset(time.perf_counter())
    detail = 0.5
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    now = time.perf_counter()
                    animation_clock.set_paused(not animation_clock.paused, now)
                elif event.key == pygame.K_r:
                    animation_clock.reset(time.perf_counter())
                elif event.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                elif event.key == pygame.K_UP:
                    animation_clock.speed = min(3.0, animation_clock.speed + 0.1)
                elif event.key == pygame.K_DOWN:
                    animation_clock.speed = max(0.1, animation_clock.speed - 0.1)
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS):
                    detail = min(2.0, detail + 0.2)
                elif event.key == pygame.K_MINUS:
                    detail = max(0.4, detail - 0.2)
                elif event.key == pygame.K_s:
                    save_screenshot(screen)
        t = animation_clock.tick(time.perf_counter())
        eye.draw(screen, t, loop_zoom(t), detail, animate=True, render_scale=1)
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
