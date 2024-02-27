def validate_integer_list(value):
    return all([isinstance(x, int) for x in value])
