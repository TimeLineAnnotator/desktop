# Golden files

Files in the current format, one for each shape the writer has to get right. The tests read each one, write it again and compare the bytes, which must be identical on every system.

They are made by a script that writes them with `json.dumps` directly, so they don't depend on the code under test. Don't edit them by hand: change the script and run it again.
