# mp_demo.py
import math
from time import time
from multiprocessing import Pool, cpu_count

def heavy_compute(n: int) -> float:
    # Fake CPU work: sum of square roots up to n
    return sum(math.sqrt(i) for i in range(n))

def main():
    nums = [5_000_000, 6_000_000, 7_000_000, 8_000_000]

    t0 = time()
    seq_results = [heavy_compute(n) for n in nums]
    t1 = time()
    print(f"Sequential time: {t1 - t0:.2f}s")

    t0 = time()
    with Pool(processes=cpu_count()) as pool:
        par_results = pool.map(heavy_compute, nums)
    t1 = time()
    print(f"Parallel time:   {t1 - t0:.2f}s")

    print("Results equal?", seq_results == par_results)

if __name__ == "__main__":
    main()
