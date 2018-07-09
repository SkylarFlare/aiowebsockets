import itertools


def fast_mask(data, mask):
    return bytes(b ^ m for b, m in zip(data, itertools.cycle(mask)))
