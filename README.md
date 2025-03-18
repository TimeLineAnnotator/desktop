<p align="center">
  <a href="https://tilia-app.com/">
    <img src="docs/img/logo.png" alt="drawing" width="100" align="center" >
  </a>
</p>
TiLiA (TimeLine Annotator) is a GUI for producing and displaying complex annotations with video and audio files. It is a full-featured but easy-to-use set of tools for researchers and enthusiasts to better analyze their media of interest without needing to rely on textual representations (like music scores). It is written in Python, using the PyQt library for its GUI.

TiLiA allows users to annotate media files primarily through timelines of various types. Each one provides different tools and enables specific annotations and visualizations. Currently, there are six types of timelines, but many more are planned.


Here are some examples TiLiA visualizations:

- Formal analysis of the Piano Sonata in C Major, K.284:
  - [First movement](https://tilia-app.com/viewer/1/)
  - [Second movement](https://tilia-app.com/viewer/2/)
  - [Third movement](https://tilia-app.com/viewer/3/)

## How to use
Instructions can be found [at the website](https://tilia-app.com/help/introduction/).

## Current features
 - 6 kinds of timelines
   - AudioWave: visualize audio files through bars that represent changes in amplitude
   - Beat: beat and measure markers with support to numbering
   - Harmony: Roman numeral and chord symbol labels using a specialized font, including proper display of inversion numerals, quality symbols and applied chords
   - Hierarchy: nested and leveled units organized in arbitrally complex hierarchical structures
   - Marker: simple, labeled markers to indicate discrete events
   - PDF: visualize PDF files synced to playback
   - Score: visualize music scores in custom, to-scale notation or conventional engraving
 - Controlling playback by clicking on timeline units
 - Multiple attributes linked to each timeline unit
 - Local audio and video support
 - YouTube stream support
 - Customizable metadata can be attached to files
 - Creation of multiple timelines
 - Timeline edition during playback
 - Toggling of timeline visibility
 - Export of audio segments based on analysis
 - Import timeline data from CSV files

## Planned features

There are many more features that we would like to implement than can be listed here, including:
- New kinds of timelines
- Range: displays units with an extension but not tied to hierarchical structures
- TiLiA explorer: allows filtered searches through timeline components across multiple TiLiA files
- Font and GUI color customization
- Video segments export
- Automatic beat detection for audio

## Online platform

The TiLiA desktop app is supported by an [online platform](https://tilia-app.com) that allows `.tla` files to be stored, visualized, shared and queried.

## Download

Visit [TiLiA's download page](https://tilia-app.com/downloads) for the latest release.

## Build from source

### Prerequisites

Before you start, you will need:
- Python 3.11 or later. You can get it at the [Python website](https://www.python.org/downloads/).
- `pip` to install dependencies.
- Git to clone the TiLiA repository. You can get it at the [Git website](https://git-scm.com/).

### How to build

Go to the desired directory and clone TiLiA with:

```
git clone https://github.com/TimeLineAnnotator/desktop.git tilia-desktop
```

Change directory to the cloned repository:
```
cd tilia-desktop
```
Note: We recommend using a [virtual environment](https://docs.python.org/3/library/venv.html) for the next steps.

Install the dependencies using pip:
```
pip install -e .
```
Install `PyInstaller` with:
```
pip install pyinstaller
```
Run PyInstaller using the settings in `tilia.spec`:
```
pyinstaller tilia.spec
```
The executable will be created in the 'dist' folder inside the project directory.

## Run TiLiA CLI

### Clone repository and install dependencies
You can follow the instructions in the previous sections to clone the repository and install dependencies.

### Run TiLiA
Use this command to run TiLiA in CLI mode:
```
python -m tilia.main --user-interface cli
```
## How to contribute

See [Contributing](./CONTRIBUTING.md).

## License

TiLiA is licensed under the Creative Commons Attribution-ShareAlike 4.0. The complete license can be found [here](./LICENSE).

## Acknowledgments

The TiLiA interface was greatly influenced by [Brent Yorgason's Audio Timeliner](https://www.singanewsong.org/audiotimeliner/). We thank the author for the development and free distribution of his software.
