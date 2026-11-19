import threading

lock = threading.Lock()
total = 0


def validate(v, limit=100):
    if v < 0 or v > limit:
        return False
    return True


def clamp(x, lo, hi):
    if x < lo and lo <= hi:
        return lo
    if x > hi:
        return hi
    return x


def add(n):
    global total
    with lock:
        total += n
    return total


def average(values):
    if len(values) == 0:
        return 0
    return sum(values) / len(values)


def process(values, lo=0, hi=10):
    out = 0
    for v in values:
        if validate(v):
            out = add(clamp(v, lo, hi))
    return out


def main():
    values = [3, 12, -4, 7]
    return process(values), average(values)
