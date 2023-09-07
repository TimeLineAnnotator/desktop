def bass_step(root_step: int, inversion: int | None):
    if inversion is None:
        return root_step
    return (root_step + 2 * inversion) % 7
