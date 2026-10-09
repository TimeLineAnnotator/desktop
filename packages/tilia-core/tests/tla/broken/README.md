# Files the reader refuses

One file for each way a file can be broken: invalid JSON, an empty file, a file that isn't a TiLiA file, a newer format, and each broken structure the reader checks for. The tests name the message, the place (a JSON Pointer) and the line they expect for each.
