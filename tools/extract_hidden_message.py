"""Extract the encrypted letter payload from an I SEE YOU MP4.

This tool intentionally imports no renderer code, payload, or secret. It reads
the public carrier geometry, repeated bits, and transport checksum from pixels.
"""

from pathlib import Path
import argparse
import os
import struct
import sys
import zlib

import cv2
import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame


CARRIER_COLUMNS = 112
CARRIER_ROWS = 16
CARRIER_FPS = 24.0
CARRIER_START_SECONDS = 0.25
CARRIER_REPEAT = 3
CARRIER_HEADER_BITS = 48
CARRIER_SYNC_BITS = "1010101011001100"
TRANSPORT_MAGIC = b"ISEEVP1"
ROW_GEOMETRY = (
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


def positions(left, right):
    return [left + (right - left) * (index + 0.5) / CARRIER_COLUMNS for index in range(CARRIER_COLUMNS)]


def frame_centres(width, height):
    eye_aspect = 2.45
    eye_width = min(width * 0.945, height * 0.69 * eye_aspect)
    eye_height = eye_width / eye_aspect
    cx, cy = width * 0.5, height * 0.52
    result = []
    for y_norm, left, right in ROW_GEOMETRY:
        y = cy + y_norm * eye_height * 0.5
        result.extend((cx + x_norm * eye_width * 0.5, y) for x_norm in positions(left, right))
    return result


def template_masks(font_size, patch_size):
    font_path = Path(r"C:\Windows\Fonts\consola.ttf")
    font = pygame.font.Font(str(font_path), font_size) if font_path.exists() else pygame.font.SysFont("dejavusansmono", font_size)
    masks = {}
    for digit in "01":
        glyph = font.render(digit, True, (255, 255, 255))
        surface = pygame.Surface((patch_size, patch_size), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 0))
        surface.blit(glyph, ((patch_size - glyph.get_width()) // 2, (patch_size - glyph.get_height()) // 2))
        alpha = pygame.surfarray.array_alpha(surface).T.astype(np.float32) / 255.0
        masks[digit] = alpha
    return masks


def correlation(roi, mask):
    roi = roi.astype(np.float32) / 255.0
    mask = mask.astype(np.float32)
    roi -= roi.mean()
    mask -= mask.mean()
    denominator = float(np.linalg.norm(roi) * np.linalg.norm(mask))
    return float(np.sum(roi * mask) / denominator) if denominator else -1.0


def classify_frame(frame, centres, masks, patch_size):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    half = patch_size // 2
    bits = []
    confidence = []
    height, width = gray.shape
    for x, y in centres:
        ix, iy = int(round(x)), int(round(y))
        if ix - half < 0 or iy - half < 0 or ix + half >= width or iy + half >= height:
            bits.append("0")
            confidence.append(-1.0)
            continue
        roi = gray[iy - half:iy + half, ix - half:ix + half]
        scores = {digit: correlation(roi, mask) for digit, mask in masks.items()}
        digit = max(scores, key=scores.get)
        bits.append(digit)
        confidence.append(scores[digit] - scores["1" if digit == "0" else "0"])
    return "".join(bits), float(np.mean(confidence))


def crop_rois(frame, centres, patch_size):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    half = patch_size // 2
    height, width = gray.shape
    rois = []
    for x, y in centres:
        ix, iy = int(round(x)), int(round(y))
        if ix - half < 0 or iy - half < 0 or ix + half >= width or iy + half >= height:
            rois.append(np.zeros((patch_size, patch_size), dtype=np.float32))
        else:
            rois.append(gray[iy - half:iy + half, ix - half:ix + half].astype(np.float32))
    return rois


def calibrated_prototypes(frame, centres, patch_size):
    known = CARRIER_SYNC_BITS + "0" * 16
    samples = {"0": [], "1": []}
    for roi, bit in zip(crop_rois(frame, centres, patch_size), known):
        samples[bit].append(roi)
    return {bit: np.mean(values, axis=0) for bit, values in samples.items()}


def classify_with_prototypes(frame, centres, prototypes, patch_size):
    bits = []
    confidence = []
    for roi in crop_rois(frame, centres, patch_size):
        scores = {digit: correlation(roi, prototype) for digit, prototype in prototypes.items()}
        digit = max(scores, key=scores.get)
        bits.append(digit)
        confidence.append(scores[digit] - scores["1" if digit == "0" else "0"])
    return "".join(bits), float(np.mean(confidence))


def bits_to_bytes(bits):
    usable = len(bits) - (len(bits) % 8)
    return bytes(int(bits[index:index + 8], 2) for index in range(0, usable, 8))


def hamming_decode_bits(bits):
    data_positions = (3, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15)
    decoded = []
    for start in range(0, len(bits) - 14, 15):
        code = [0] + [int(bit) for bit in bits[start:start + 15]]
        syndrome = sum(parity for parity in (1, 2, 4, 8) if sum(code[position] for position in range(1, 16) if position & parity) % 2) 
        if 0 < syndrome < 16:
            code[syndrome] ^= 1
        decoded.extend(str(code[position]) for position in data_positions)
    return "".join(decoded)


def recover(video_path):
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    frame_count = 0
    block_samples = {}
    total_blocks = None
    pygame.init()
    try:
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError("Video has no readable frames")
        height, width = frame.shape[:2]
        patch_size = max(16, int(round(width / 1280 * 24)))
        patch_size += patch_size % 2  # Match even-sized ROIs to the template.
        font_size = max(7, int(round(width / 1280 * 12)))
        masks = template_masks(font_size, patch_size)
        while ok:
            frame_count += 1
            height, width = frame.shape[:2]
            bits, confidence = classify_frame(frame, frame_centres(width, height), masks, patch_size)
            if frame_count >= int(round(CARRIER_START_SECONDS * CARRIER_FPS)) + 1:
                if bits[:len(CARRIER_SYNC_BITS)] != CARRIER_SYNC_BITS:
                    ok, frame = capture.read()
                    continue
                block = int(bits[16:32], 2)
                advertised_blocks = int(bits[32:48], 2)
                if advertised_blocks <= 0 or advertised_blocks > 10000 or block >= advertised_blocks:
                    ok, frame = capture.read()
                    continue
                total_blocks = advertised_blocks if total_blocks is None else total_blocks
                if advertised_blocks != total_blocks:
                    ok, frame = capture.read()
                    continue
                block_samples.setdefault(block, []).append(bits[CARRIER_HEADER_BITS:])
            ok, frame = capture.read()
    finally:
        capture.release()
        pygame.quit()
    if total_blocks is None or any(index not in block_samples for index in range(total_blocks)):
        raise RuntimeError(f"Payload blocks were not recovered from {frame_count} frames")
    data_bits = "".join(
        max(column, key=column.count)
        for index in range(total_blocks)
        for column in zip(*block_samples[index])
    )
    encoded_bits = "".join(
        max(data_bits[index:index + CARRIER_REPEAT], key=data_bits[index:index + CARRIER_REPEAT].count)
        for index in range(0, len(data_bits) - CARRIER_REPEAT + 1, CARRIER_REPEAT)
    )
    candidate = bits_to_bytes(hamming_decode_bits(encoded_bits))
    if candidate[:len(TRANSPORT_MAGIC)] == TRANSPORT_MAGIC and len(candidate) >= len(TRANSPORT_MAGIC) + 8:
        payload_start = len(TRANSPORT_MAGIC) + 4
        payload_length = struct.unpack(">I", candidate[len(TRANSPORT_MAGIC):payload_start])[0]
        payload_end = payload_start + payload_length
        if len(candidate) >= payload_end + 4:
            payload = candidate[payload_start:payload_end]
            expected_crc = struct.unpack(">I", candidate[payload_end:payload_end + 4])[0]
            if zlib.crc32(payload) & 0xffffffff == expected_crc:
                return payload, frame_count, total_blocks
    raise RuntimeError(f"Payload checksum failed after {frame_count} frames")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    message, frames, blocks = recover(args.video)
    if args.output:
        args.output.write_bytes(message)
        print(args.output)
    print(f"encrypted_payload_bytes={len(message)} frames={frames} blocks={blocks}")


if __name__ == "__main__":
    main()

