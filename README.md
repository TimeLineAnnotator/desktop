<p align="center">
  <a href="https://tilia-app.com/">
    <img src="tilia/ui/icons/hicolor/apps/256/tilia.svg" alt="drawing" width="100" >
  </a>
</p>
TiLiA (TimeLine Annotator) is a GUI for producing and displaying complex annotations with video and audio files. It is a full-featured, easy-to-use set of tools for researchers and enthusiasts to better analyze their media of interest without needing to rely on textual representations (like music scores). It is written in Python, using the PySide library for its GUI.

TiLiA allows users to annotate media files primarily through timelines of various types. Each one provides different tools and enables specific annotations and visualizations. Currently, there are seven types of timelines, but many more are planned.

<p align="center">
  <img src="docs/img/tilia-desktop.png" width="600" alt="TiLiA desktop interface" >
</p>

Here are some examples of TiLiA visualizations:

- Formal analysis of the Piano Sonata in D Major, K.284:
  - [First movement](https://tilia-app.com/viewer/135/)
  - [Second movement](https://tilia-app.com/viewer/136/)
  - [Third movement](https://tilia-app.com/viewer/137/)


## Current features
- 7 kinds of timelines
    - AudioWave: visualize audio files through bars that represent changes in amplitude
    - Beat: beat and measure markers with support for numbering
    - Harmony: Roman numeral and letter symbol labels using a specialized font, including proper display of inversion numerals, quality symbols and applied chords
    - Hierarchy: nested and levelled units organized in arbitrarily complex hierarchical structures
    - Marker: simple, labelled markers to indicate discrete events
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
TiLiA has releases for Windows, macOS and Linux. [Download them here](https://github.com/TimeLineAnnotator/desktop/releases/). Instructions to install are [on our website](https://tilia-app.com/help/introduction/).

Tutorials on how to use TiLiA can be found on our [website](https://tilia-app.com/help/) or in these [videos](https://www.youtube.com/@tilia-app).

## Build or run from source

TiLiA can also be run and built from source.

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

### Note to Linux users
Users have reported dependency issues when running TiLiA on Linux (see [#370](https://github.com/TimeLineAnnotator/desktop/issues/370) and [#371](https://github.com/TimeLineAnnotator/desktop/issues/371)).
Due to system variations between Linux distributions, some additional system dependencies may be required. Visit our [help page](https://tilia-app.com/help/installation#troubleshooting-linux) for more information.

### Running from source


- Clone TiLiA with:

```
git clone https://github.com/TimeLineAnnotator/desktop.git tilia-desktop
```

- Change directory to the cloned repository:
```
cd tilia-desktop
```
> Note: We recommend using a clean [virtual environment](https://docs.python.org/3/library/venv.html) for the next steps.
Failure to do so may cause dependency issues.

- Install TiLiA and its dependencies with:
```
pip install -e .
```

- To run TiLiA from source, run:
```
tilia
```

- TiLiA also offers a CLI mode, which can be run with:
```
tilia --user-interface cli
```
> Note: The CLI is currently only available when run from source, and not in the compiled executable.

### Building from source
TiLiA uses [Nuitka](https://nuitka.net/) to build binaries.
Note that the binaries will be for the platform you are building on, as `Nuitka` supports no cross-compilation.

- After cloning TiLiA, install TiLiA's run and build dependencies with:
```
pip install -e . --group build
```
- To build a stand-alone executable, run the script:
```
python scripts/deploy.py [ref_name] [os_type]
```
> Note: `ref_name` and `os_type` are arbitrary strings that do not affect the build outcome.

The executable will be found in the `build/[os_type]/exe` folder in the project directory.

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
