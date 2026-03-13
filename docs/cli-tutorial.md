# TiLiA CLI Tutorial

This tutorial shows how the TiLiA CLI can be used to perform some common tasks.

## Setup

### Installation

See [README.md](README.md) detailed installation instructions.

### Running the CLI

The CLI can be run from source code as follows:
```bash
python -m tilia.main --user-interface cli
```

You can also run it from a TiLiA binary:
```bash
cd "C:/Program Files/TiLiA"
./tilia --interface cli
```

TiLiA CLI is an interactive shell. You'll see ``>>>`` when it's ready for your input.

### Getting Help

For any command, you can get detailed help and examples by typing a command followed by `--help`:

```bash
>>> timelines add --help
usage: main.py timelines add [-h] [--name NAME] [--height HEIGHT] [--beat-pattern BEAT_PATTERN [BEAT_PATTERN ...]] {hierarchy,hrc,marker,mrk,beat,bea,score,sco}

positional arguments:
  {hierarchy,hrc,marker,mrk,beat,bea,score,sco}
                        Kind of timeline to add

options:
  -h, --help            show this help message and exit
  --name NAME, -n NAME  Name of the new timeline
  --height HEIGHT, -e HEIGHT
                        Height of the timeline
  --beat-pattern BEAT_PATTERN [BEAT_PATTERN ...], -b BEAT_PATTERN [BEAT_PATTERN ...]
                        Pattern as space-separated integers indicating beat count in a measure. Pattern will be repeated. Pattern '3 4', for instance, will alternate measures of 3 and 4 beats.

Examples:
  timelines add beat --name "Measures" --beat-pattern 4
  timelines add hierarchy --name "Form"
  timelines add marker --name "Cadences"
```

---

##  Creating a New Project from Media

These commands can be used to create a TiLiA project, load a media file, create timelines, and organize them.

Load a media file:
```bash
load-media "C:/path/to/audio.mp3" # Local file
load-media "https://www.youtube.com/watch?v=..." # YouTube video
```

Set the media duration manually:
```bash
metadata set-media-length 300 # 300 seconds = 5 minutes
```

Set some basic metadata about the piece:
```bash
metadata set title "Bohemian Rhapsody"
metadata set composer "Freddie Mercury"
metadata set performer "Queen"
```

Display metadata with:
```bash
metadata show
```
The output should be something like this:
```bash
Title: Bohemian Rhapsody
Notes:
Composer: Freddie Mercury
Performer: Queen
...
Media length: 300.0
```

Now that a media is loaded, and metadata is set, we can create timelines:
```bash
timelines add beat --name "Measures" --beat-pattern 4
timelines add hierarchy --name "Form"
timelines add marker --name "Cadences"
```

To display existing timelines use:
```bash
timelines list
```
This should output:
```bash
+------+----------+-----------+
| ord. |   name   |    kind   |
+------+----------+-----------+
|  1   |          |   Slider  |
|  2   | Measures |    Beat   |
|  3   |   Form   | Hierarchy |
|  4   | Cadences |   Marker  |
+------+----------+-----------+
```

Note that you must have a media loaded or a manually set duration to create timelines.

## Organizing Timelines

After creating timelines, you might want to reorder or remove some.

```bash
timelines add hierarchy --name "Form"
timelines add marker --name "Themes"
timelines add beat --name "Measures" --beat-pattern 4
timelines add marker --name "Cadences"
timelines list

# Output
+------+----------+-----------+
| ord. |   name   |    kind   |
+------+----------+-----------+
|  1   |   Form   | Hierarchy |
|  2   |  Themes  |   Marker  |
|  3   | Measures |    Beat   |
|  4   | Cadences |   Marker  |
+------+----------+-----------+
```

Reorder timelines:

```bash
# Move "Measures" to the top (position 1)
timelines move name "Measures" 1

# Move the timeline at position 4 (Cadences) to position 2
timelines move ordinal 4 2
```

Remove a timeline we don't need anymore:
```
timelines remove name "Themes"
```

Check the final arrangement:
```
timelines list

# Output
+------+----------+-----------+
| ord. |   name   |    kind   |
+------+----------+-----------+
|  1   | Measures |    Beat   |
|  2   | Cadences |   Marker  |
|  3   |   Form   | Hierarchy |
+------+----------+-----------+
```

## Importing Annotations from CSV

If you have annotations in CSV format (perhaps made with another tool), you can import them.

First, let's look at the CSV files we'll import:

**form.csv:**
```csv
start,end,level,label,comments
0.0,30.0,1,Introduction,
30.0,90.0,1,Verse 1,
35.0,50.0,2,Phrase A,
50.0,65.0,2,Phrase B,
90.0,150.0,1,Chorus,
```

**cadences.csv:**
```csv
time,label,comments
29.5,HC,Half Cadence
89.3,PAC,Perfect Authentic Cadence
149.8,PAC,
```

For detailed CSV format specifications, see: https://tilia-app.com/help/import

To import the CSV files:

```bash
# Set up the project
load-media "C:/audio/song.mp3"
timelines add hierarchy --name "Form"
timelines add marker --name "Cadences"

# Import hierarchies from CSV (using time values)
timelines import hierarchy by-time --file "C:/data/form.csv" --target-name "Form"

# Import markers from CSV (using time values)
timelines import marker by-time --file "C:/data/cadences.csv" --target-name "Cadences"

```
When you have beat/measure information, you can import annotations using measure numbers instead of absolute time.

Here we will also be importing beats from a CSV file, but they could come from an existingTiLiA file.

**beats.csv:**
```csv
time
0.0
0.6
1.2
1.8
2.4
3.0
```
Hierarchy timeline CSV data:

**form_measures.csv:**
```csv
start_measure,start_fraction,end_measure,end_fraction,level,label,comments
1,0.0,8,0.0,1,Introduction,
9,0.0,24,0.0,1,Verse,
9,0.0,16,0.0,2,Phrase A,
17,0.0,24,0.0,2,Phrase B,
```

Now import them:

```bash
# Set up with a beat timeline
load-media "C:/audio/piece.mp3"
timelines add beat --name "Measures" --beat-pattern 4
timelines add hierarchy --name "Form"

# Import beat data first
timelines import beat --file "C:/data/beats.csv" --target-name "Measures"

# Now import hierarchies using measure numbers
timelines import hierarchy by-measure --file "C:/data/form_measures.csv" --target-name "Form" --reference-tl-name "Measures"

```

## Working with Existing TiLiA files

You can also open and modify existing TiLiA files.

Open an existing file:
```bash
open "C:/projects/song.tla"
timelines list

# Output
+-----+----------+-----------+
| ord. | name    | kind      |
+-----+----------+-----------+
| 1   | Measures| Beat       |
| 2   | Form    | Hierarchy  |
| 3   | Cadences| Marker     |
+-----+----------+-----------+
```

Now let's add a new timeline and import some data into it:

```bash
timelines add marker --name "Dynamics"
timelines import marker by-time --file "C:/data/dynamics.csv" --target-name "Dynamics"
save "C:/projects/song.tla" --overwrite
```

We can also export the file to JSON for use in other tools:

```bash
export "C:/exports/song.json" --overwrite
```

---

## Automation with CLI Scripts

You can create a `.txt` file with a sequence of commands to automate repetitive tasks, so you don't have to type them every time.

**process_song.txt**
```
# Load and set up project
load-media "C:/audio/song.mp3"
metadata set title "Example Song"
metadata set composer "John Doe"

# Create timeline structure
timelines add beat --name "Measures" --beat-pattern 4
timelines add hierarchy --name "Form"
timelines add marker --name "Cadences"

# Import all annotations
timelines import beat --file "C:/data/beats.csv" --target-name "Measures"
timelines import hierarchy by-measure --file "C:/data/form.csv" --target-name "Form" --reference-tl-name "Measures"
timelines import marker by-measure --file "C:/data/cadences.csv" --target-name "Cadences" --reference-tl-name "Measures"

# Save the result
save "C:/projects/song.tla" --overwrite
```

Then run it from the CLI with the `script` command:

```bash
# Run the script
script "C:/scripts/process_song.txt"
```

**Script features:**
- Lines starting with `#` are comments and are ignored
- Empty lines are ignored
- Commands execute sequentially
- Script stops on first error

For processing multiple files, you can use any programming language to generate a single CLI script containing commands for each file.

**batch_process.py**:

```python
from pathlib import Path

# Configuration
audio_dir = Path("C:/audio")
data_dir = Path("C:/data")
output_dir = Path("C:/projects")
script_file = Path("C:/temp/tilia_script.txt")

# Files to process
songs = ["song1", "song2", "song3"]
script_content = ""

for song in songs:
    # Generate CLI script
    script_content += f"""
# Process {song}
load-media "{audio_dir / song}.mp3"
metadata set title "{song}"

# Create timelines
timelines add beat --name "Measures" --beat-pattern 4
timelines add hierarchy --name "Form"
timelines add marker --name "Cadences"

# Import data
timelines import beat --file "{data_dir / song}_beats.csv" --target-name "Measures"
timelines import hierarchy by-measure --file "{data_dir / song}_form.csv" --target-name "Form" --reference-tl-name "Measures"
timelines import marker by-measure --file "{data_dir / song}_cadences.csv" --target-name "Cadences" --reference-tl-name "Measures"

# Save and clear
save "{output_dir / song}.tla" --overwrite
clear --force
"""

# Write script
with open(script_file, 'w') as f:
    f.write(script_content)

```
