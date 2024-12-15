<p align="center">
  <a href="https://tilia-app.com/">
    <img src="docs/img/logo.png" alt="drawing" width="100" align="center" >
  </a>
</p>
TiLiA (TimeLine Annotator) is a GUI for producing and displaying complex annotations over video and audio files. It is a full-featured but easy-to-use set of tools for researchers and enthusiasts to better analyze their media of interest without needing to rely on textual representations (like music scores). It is written in Python, using the PyQt library for its GUI.

TiLiA allows users to annotate media files primarily through timelines of various types. Each one provides different tools and enables specific annotations and visualizations. Currently, there are four types of timelines (hierarchy, marker, beat and harmony) but many more are planned.

Some examples of what TiLiA visualizations look like:

- Formal analysis of the Piano Sonata in C Major, K.284:
  - [First movement](https://www.timelineannotator.com/examples/mozart-k284-i)
  - [Second movement](https://www.timelineannotator.com/examples/mozart-k284-ii)
  - [Third movement](https://www.timelineannotator.com/examples/mozart-k284-iii)

## How to use
Instructions can be found [at the website](https://tilia-app.com/help/introduction/).

## Current features
 - 6 kinds of timelines
   - AudioWave: visualise audio files through bars that represent changes in amplitude
   - Beat: beat and measure markers with support to numbering
   - Harmony: Roman numeral and chord symbol labels using a specialized font, including proper display of inversion numerals, quality symbols and applied chords
   - Hierarchy: nested and levelled units organized in arbitrally complex hierarchical structures
   - Marker: simple labelled markers to indicate discrete events
   - PDF: visualize PDF files synced to playback
   - Score: visualize music scores in a custom, to-scale notation or in conventional engraving
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

There are many more features that I would like to implement than can be listed here. Some of the more interesting ones are listed below.
- New kinds of timelines
  - Range: displays units with an extension, but not tied to hierarchical structures
  - Musical score: displays audio-aligned musical scores
- TiLiA explorer: allows filtered searches through timeline components in multiple TiLiA files
- Font and GUI colors customization
- Video segments exporting
- Automatic cut detection for video
- Automatic beat detection for audio

## Online platform

The TiLiA desktop app is supported by an [online platform](https://tilia-app.com) that allows `.tla` files to be stored, visualized, shared and queried.

## Build from source

### Prerequisites

Before you start, you'll need to have Python 3.11 or later installed on your system. If you don't have it, download the installer from the [official Python website](https://www.python.org/downloads/) and follow their instructions.

### How to build
#### Install PyInstaller
In your terminal or command prompt, type the following command and press Enter:
```
pip install pyinstaller
```

#### Clone the TiLiA Repository
Open a terminal or command prompt and navigate to the directory where you want to save the project.
Execute the following command:
```
git clone https://github.com/TimeLineAnnotator/desktop.git
```

#### Build with PyInstaller
Navigate into the newly downloaded TiLiA project directory:
```
cd TiLiA
```
Run PyInstaller using the provided spec file:
```
pyinstaller tilia.spec
```

#### After Building

You'll find your executable application files within a newly created 'dist' folder inside the TiLiA directory.

## How to contribute

Read the CONTRIBUTING.md file in the root directory.

## License

TiLiA is licensed under the Creative Commons Attribution-ShareAlike 4.0. The complete license can be found in the LICENSE file in this directory.

## Acknowledgments

The TiLiA interface was greatly influenced by Brent Yorgason's Audio Timeliner, which can be found at https://www.singanewsong.org/audiotimeliner/. I thank the author for the development and free distribution of his software.

