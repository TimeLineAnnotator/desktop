<p align="center">
  <a href="https://tilia-app.com/">
    <img src="docs/img/logo.png" alt="drawing" width="100" >
  </a>
</p>
TiLiA (TimeLine Annotator) is a GUI for producing and displaying complex annotations with video and audio files. It is a full-featured but easy-to-use set of tools for researchers and enthusiasts to better analyze their media of interest without needing to rely on textual representations (like music scores). It is written in Python, using the PySide library for its GUI.

TiLiA allows users to annotate media files primarily through timelines of various types. Each one provides different tools and enables specific annotations and visualizations. Currently, there are six types of timelines, but many more are planned.

<p align="center">
  <img src="docs/img/tilia-desktop.png" width="600" alt="TiLiA desktop interface" >
</p>

Here are some examples TiLiA visualizations:

- Formal analysis of the Piano Sonata in D Major, K.284:
  - [First movement](https://tilia-app.com/viewer/135/)
  - [Second movement](https://tilia-app.com/viewer/136/)
  - [Third movement](https://tilia-app.com/viewer/137/)


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
- Command-line interface (see the CLI [help page](docs/cli-tutorial.md) for more information)

## How to install and use
TiLiA has releases for Windows, macOS and Linux. Instructions to download and run are [at the website](https://tilia-app.com/help/introduction/).

Tutorials on how to use TiLiA can be found at the [website](https://tilia-app.com/help/) or in video [here](https://www.youtube.com/@tilia-app).

## Build or run from source

TiLiA can be also run and build from source.

### Prerequisites

Before you start, you will need:
- Python 3.10 - 3.12. Download from the [Python website](https://www.python.org/downloads/). (Support for Python 3.13 is variable due to the dependencies used.)
- <details>
  <summary>Other pre-requisites</summary>

    | Package | Installation | Notes |
    | --- | --- | --- |
    | `pip` | `python -m ensurepip --upgrade` |  `pip` should come with your Python installation |
    | `git` | Download [here](https://git-scm.com/install) | Not necessary for a direct download from this repository |
  </details>

### Note for Linux users
Users have reported dependency issues when running TiLiA on Linux (see [#370](https://github.com/TimeLineAnnotator/desktop/issues/370) and [#371](https://github.com/TimeLineAnnotator/desktop/issues/371)).
That is probably due to `PyInstaller` not being completely compatible with `PyQt`.
We are working to fix that with with a new build process using `pyside6-deploy` instead.

### Running from source


Clone TiLiA with:

```
git clone https://github.com/TimeLineAnnotator/desktop.git tilia-desktop
```

Change directory to the cloned repository:
```
cd tilia-desktop
```
Note: We recommend using a clean [virtual environment](https://docs.python.org/3/library/venv.html) for the next steps.
Failure to do so is likely to cause issues with dependencies.

Install TiLiA and its dependencies with:
```
pip install -e .
```
On Linux, some additional Qt dependencies are required:
```
sudo apt install libnss3 libasound libxkbfile1 libpulse0
```
| n.b.: the specific names of these packages varies based on your Linux distribution.

To run TiLiA from source, run:
```
tilia-desktop
```

TiLiA also offers a CLI mode, which can be run with:
```
python -m tilia --user-interface cli
```

### Building from source
TiLiA uses [PyInstaller](https://pyinstaller.org/en/stable/) to build binaries.
Note that the binaries will be for the platform you are building on, as `PyInstaller` supports no cross-compilation.

After cloning tilia and installing the dependencies (see above), install `PyInstaller` with:
```
pip install pyinstaller
```
To build a stand-alone executable, run PyInstaller with the settings in `tilia.spec`:
```
pyinstaller tilia.spec
```
The executable will be created in `dist` folder inside the project directory.

## Planned features

There are many more features that we would like to implement than can be listed here, including:
- New kinds of timelines, for instance a "range" timeline that displays units with an extension but not tied to hierarchical structures
- TiLiA explorer: allows filtered searches through timeline components across multiple TiLiA files
- Font and GUI color customization
- Video segments export
- Automatic beat detection for audio

## Online platform

The TiLiA desktop app is supported by an [online platform](https://tilia-app.com) that allows `.tla` files to be stored, visualized, shared and queried.

## How to contribute

See [Contributing](./CONTRIBUTING.md).

## License

TiLiA is licensed under the GNU General Public License (version 3). The complete license can be found [here](./LICENSE).

## Acknowledgments

The TiLiA interface was greatly influenced by [Brent Yorgason's Audio Timeliner](https://www.singanewsong.org/audiotimeliner/). We thank the author for the development and free distribution of his software.
