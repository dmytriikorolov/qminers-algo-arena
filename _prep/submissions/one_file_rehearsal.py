"""Self-contained packaging rehearsal. This is NOT an official API/signature."""


def solve(data):
    result = []
    total = 0
    for value in data:
        total += value
        result.append(total)
    return result
