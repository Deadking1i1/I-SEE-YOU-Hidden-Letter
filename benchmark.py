import statistics
import time

import pygame

from main import Eye, loop_zoom


pygame.init()
screen = pygame.Surface((1920, 1080))
eye = Eye()
times = []
for i in range(120):
    start = time.perf_counter()
    screen.fill((0, 0, 3))
    eye.draw(screen, i / 60.0, loop_zoom(i / 60.0), 2.0)
    times.append(time.perf_counter() - start)
pygame.quit()
times.sort()
print(f"frames={len(times)} average_fps={1/statistics.mean(times):.2f} "
      f"p50_ms={statistics.median(times)*1000:.2f} p95_ms={times[int(.95*len(times))-1]*1000:.2f} "
      f"p99_ms={times[int(.99*len(times))-1]*1000:.2f}")
