import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import pygame

from main import (
    AnimationClock,
    BINARY_DIGITS,
    DEFAULT_RENDER_PROFILE,
    Eye,
    CARRIER_DATA_BITS,
    CARRIER_ROWS,
    CARRIER_COLUMNS,
    CARRIER_REPEAT,
    CARRIER_SYNC_BITS,
    CARRIER_TOTAL_BLOCKS,
    VISUAL_CARRIER_BITS,
    METRICS,
    inside_eye,
    loop_zoom,
    blink_amount,
    gaze_offset,
    carrier_frame_bits,
    squint_amount,
    squint_sweep,
    lower_lid_y,
    render_frame,
    sample_cubic_arc,
    save_screenshot,
    upper_lid_y,
)


def test_binary_configuration_and_loop_continuity():
    assert BINARY_DIGITS == "01"
    assert METRICS["eye_aspect"] == 2.45
    assert loop_zoom(0) == loop_zoom(9) == 0.0
    assert abs(loop_zoom(0) - loop_zoom(18)) < 1e-9


def test_public_visual_carrier_is_binary_and_moves_across_animation_frames():
    assert VISUAL_CARRIER_BITS
    assert set(VISUAL_CARRIER_BITS) <= set(BINARY_DIGITS)
    frame = carrier_frame_bits(0)
    assert len(frame) == CARRIER_ROWS * CARRIER_COLUMNS
    assert len(frame) - CARRIER_DATA_BITS == len(CARRIER_SYNC_BITS) + 32
    assert frame[:len(CARRIER_SYNC_BITS)] == CARRIER_SYNC_BITS
    assert carrier_frame_bits(CARRIER_TOTAL_BLOCKS) == frame


def test_headless_binary_frame_contains_nonblack_pixels():
    frame = render_frame(12.0, (320, 180), 0.5)
    assert frame.get_size() == (320, 180)
    assert pygame.surfarray.array3d(frame).max() > 0


def test_background_is_black_and_background_renderer_is_removed():
    assert not hasattr(Eye, "_draw_background")
    pixels = pygame.surfarray.array3d(render_frame(12.0, (320, 180), 0.5))
    assert pixels[:, :15].max() == 0
    assert tuple(pixels[0, 0]) == (0, 0, 0)


def test_renderer_startup_and_binary_eye():
    pygame.init()
    eye = Eye()
    assert eye._eye_dimensions(960, 540)[0] / eye._eye_dimensions(960, 540)[1] == METRICS["eye_aspect"]
    pygame.quit()


def test_measured_lid_geometry_is_open_and_asymmetric():
    samples = [i / 400 for i in range(401)]
    openings = [lower_lid_y(x) - upper_lid_y(x) for x in samples]
    assert min(openings) >= 0.0
    assert max(openings) > 0.35
    assert any(abs(upper_lid_y(x) - upper_lid_y(1.0 - x)) > 0.01 for x in samples)
    assert inside_eye(0.5, 0.5)
    assert not inside_eye(0.5, -0.2)


def test_left_lid_endpoints_share_one_corner():
    assert upper_lid_y(0.0) == lower_lid_y(0.0) == 0.5
    assert lower_lid_y(0.001) - upper_lid_y(0.001) > 0.0
    assert upper_lid_y(1.0) == lower_lid_y(1.0) == 0.47
    assert lower_lid_y(0.999) - upper_lid_y(0.999) > 0.0


def test_optional_reference_profile_preserves_binary_renderer_contract():
    assert DEFAULT_RENDER_PROFILE["iris_font_scale"] == 1.0
    pygame.init()
    try:
        eye = Eye(profile={"body_density": 0.9, "iris_spacing": 3.0})
        assert eye.profile["body_density"] == 0.9
        assert eye.profile["iris_spacing"] == 3.0
        assert eye.profile["iris_font_scale"] == 1.0
        frame = pygame.Surface((320, 180))
        eye.draw(frame, 12.0, 0.0, 0.5, render_scale=2)
        assert pygame.surfarray.array3d(frame).max() > 0
    finally:
        pygame.quit()


def test_approved_iris_and_pupil_ratios_remain_locked():
    eye = Eye()
    eye_width, _ = eye._eye_dimensions(2560, 1440)
    iris_rx = eye_width * METRICS["iris_width_fraction"] * 0.5
    pupil_rx = iris_rx * METRICS["pupil_width_fraction"]
    assert (2.0 * iris_rx) / eye_width == METRICS["iris_width_fraction"]
    assert abs(pupil_rx / iris_rx - METRICS["pupil_width_fraction"]) < 1e-12


def test_contour_sampling_reaches_both_endpoints_with_stable_spacing():
    samples = sample_cubic_arc(((0.0, 0.0), (0.1, 0.8), (0.8, 0.1), (1.0, 1.0)), 32)
    assert samples[0] == (0.0, 0.0)
    assert samples[-1] == (1.0, 1.0)
    distances = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(samples, samples[1:])]
    assert max(distances) / min(distances) < 1.8


def test_row_bounds_follow_the_opening_mask():
    eye = Eye()
    for y in (-0.4, -0.1, 0.2, 0.3):
        bounds = eye._row_bounds(y)
        assert bounds is not None
        assert -1.0 <= bounds[0] < bounds[1] <= 1.0


def test_cached_lid_lookup_preserves_bezier_geometry():
    eye = Eye()
    errors = []
    for index in range(101):
        x = -1.0 + 2.0 * index / 100.0
        cached_upper, cached_lower = eye._lid_bounds(x)
        u = (x + 1.0) * 0.5
        exact_upper = 2.0 * upper_lid_y(u) - 1.0
        exact_lower = 2.0 * lower_lid_y(u) - 1.0
        errors.extend((abs(cached_upper - exact_upper), abs(cached_lower - exact_lower)))
    assert max(errors) < 0.0005


def test_glyph_bbox_clipping_rejects_lid_overflow():
    eye = Eye()
    assert eye._glyph_fits_eye(50, 50, 80, 40, (46, 50, 54, 54))
    assert not eye._glyph_fits_eye(50, 50, 80, 40, (46, 20, 54, 30))
    assert not eye._glyph_fits_eye(50, 50, 80, 40, (8, 45, 18, 55))
    assert not eye._glyph_fits_eye(50, 50, 80, 40, (82, 45, 92, 55))


def test_static_geometry_is_deterministic_and_iris_can_be_suppressed():
    silhouette = render_frame(12.0, (320, 180), 0.5, draw_iris=False)
    complete = render_frame(12.0, (320, 180), 0.5, draw_iris=True)
    repeat = render_frame(12.0, (320, 180), 0.5, draw_iris=True)
    assert pygame.surfarray.array3d(complete).tobytes() == pygame.surfarray.array3d(repeat).tobytes()
    assert pygame.surfarray.array3d(silhouette).tobytes() != pygame.surfarray.array3d(complete).tobytes()


def test_reused_glyph_cache_is_pixel_consistent():
    pygame.init()
    try:
        eye = Eye()
        first = pygame.Surface((320, 180))
        second = pygame.Surface((320, 180))
        eye.draw(first, 12.0, 0.0, 0.5)
        cache_sizes = (len(eye.font_cache), len(eye.rotated_cache), len(eye.row_bounds_cache))
        eye.draw(second, 12.0, 0.0, 0.5)
        assert pygame.surfarray.array3d(first).tobytes() == pygame.surfarray.array3d(second).tobytes()
        assert cache_sizes == (len(eye.font_cache), len(eye.rotated_cache), len(eye.row_bounds_cache))
    finally:
        pygame.quit()


def test_screenshot_export(tmp_path):
    pygame.init()
    screen = pygame.Surface((64, 36))
    path = save_screenshot(screen, tmp_path)
    assert path.exists() and path.suffix == ".png"
    pygame.quit()


def test_animation_clock_pause_resume_preserves_elapsed_time():
    clock = AnimationClock()
    clock.reset(0.0)
    assert clock.tick(1.0) == 1.0
    clock.set_paused(True, 1.0)
    assert clock.tick(5.0) == 1.0
    clock.set_paused(False, 5.0)
    assert clock.tick(6.0) == 2.0


def test_animated_frames_change_without_losing_binary_eye():
    first = render_frame(4.0, (320, 180), 0.5, animate=True)
    second = render_frame(8.0, (320, 180), 0.5, animate=True)
    assert pygame.surfarray.array3d(first).max() > 0
    assert pygame.surfarray.array3d(second).max() > 0
    assert pygame.surfarray.array3d(first).tobytes() != pygame.surfarray.array3d(second).tobytes()


def test_animated_eye_forms_once_but_digits_keep_moving():
    formed = render_frame(8.0, (320, 180), 0.5, animate=True)
    later = render_frame(18.0, (320, 180), 0.5, animate=True)
    much_later = render_frame(36.0, (320, 180), 0.5, animate=True)
    assert pygame.surfarray.array3d(formed).max() > 0
    assert pygame.surfarray.array3d(formed).tobytes() != pygame.surfarray.array3d(later).tobytes()
    assert pygame.surfarray.array3d(later).tobytes() != pygame.surfarray.array3d(much_later).tobytes()


def test_gaze_and_blink_are_available_after_formation():
    assert gaze_offset(0.0) != gaze_offset(12.0)
    assert blink_amount(2.0) == 0.0
    assert max(blink_amount(value) for value in (8.0, 8.1, 8.2, 8.3, 8.4)) > 0.0


def test_squint_slowly_sweeps_gaze_left_to_right():
    assert squint_amount(10.9) == 0.0
    assert max(squint_amount(value) for value in (12.0, 13.0, 16.0)) > 0.0
    assert squint_sweep(11.0) < squint_sweep(21.0)


def test_blink_uses_upper_lid_but_squint_uses_both_lids():
    eye = Eye()
    base_upper, base_lower = eye._lid_bounds(0.0)
    eye._blink = 1.0
    blink_upper, blink_lower = eye._lid_bounds(0.0)
    assert blink_upper == base_lower
    assert blink_lower == base_lower
    eye._blink = 0.0
    eye._squint = 0.34
    squint_upper, squint_lower = eye._lid_bounds(0.0)
    assert squint_upper > base_upper
    assert squint_lower < base_lower


def test_persistent_animation_cache_does_not_wrap_after_formation():
    pygame.init()
    try:
        eye = Eye()
        first = pygame.Surface((320, 180))
        later = pygame.Surface((320, 180))
        eye.draw(first, 17.99, 0.0, 0.5, animate=True, render_scale=1)
        eye.draw(later, 18.01, 0.0, 0.5, animate=True, render_scale=1)
        assert pygame.surfarray.array3d(first).tobytes() != pygame.surfarray.array3d(later).tobytes()
    finally:
        pygame.quit()
