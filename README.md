# TiLiA

---

TiLiA (TimeLine Annotator) is an open-source GUI for producing and displaying complex annotations over video and audio files. It is a full-featured but easy to use set of tools for researchers and enthusiasts to better analyze their media of interest without needing to rely on textual representations (like music scores). It is written in Python, using the PyQt library for its GUI.

TiLiA allows user to annotate media files is primarily through timelines of various types. Each one provides different tools and enables specific annotations and visualizations. Currently, there are four types of timelines (hierarchy, marker, beat and harmony) but many more are planned.

Some examples of what TiLiA visualizations look like:

- Formal analysis of the Piano Sonata in C Major, K.284:
  - [First movement](https://www.timelineannotator.com/examples/mozart-k284-i)
  - [Second movement](https://www.timelineannotator.com/examples/mozart-k284-ii)
  - [Third movement](https://www.timelineannotator.com/examples/mozart-k284-iii)

## Current features
 - 4 different kinds of timelines
   - Hierarchy: nested and leveled units organized in arbitrally complex hierarchical structures
   - Marker: simple labeled markers to indicate discrete events
   - Beat: beat and measure markers with support to numbering
   - Harmony: roman numeral and chord symbol labels using a specialized font, including properly display of inversion numerals, quality symbols and applied chords.
 - Controlling playback by clicking on timeline units
 - Multiple attributes linked to each timeline units
 - Local audio and video support
 - YouTube stream support
 - Customizable metadata can be attached to files
 - Creation of multiple timelines
 - Easy timeline edition during playback
 - Toggling of timleine visibility
 - Export of audio segments based on analysis
 - Import timeline components from CSV files

## Planned features

There are many more features that I would like to implement than can be listed here. Some of the more interesting ones are listed below.
- Improvements to timelines:
  - Hierarchy:
    - Length, start and end also displayed in terms of beats and measures
  - Beat:
    - Change beats in measure for multiple measures
- New kinds of timelines
  - Range: displays units with an extension, but not tied to hierarchical structures
  - Audio wave
  - PDF: display and synchronize navigation of PDF files with playback
- TiLiA explorer: allows filtered searches through timeline components in multiple TiLiA files
- Font and GUI colors customization
- Video segments exporting
- Automatic cut detection for video
- Automatic beat detection for audio

## Website

Releases and (incomplete) documentation can be found at https://tilia-ad98d.web.app/

## Build from source

### Prerequisites

Before you start, you'll need to have Python 3.11 or later installed on your system. If you don't have it, download the installer from the official Python website ([https://www.python.org/downloads/](https://www.python.org/downloads/)) and follow their instructions.

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
git clone https://github.com/FelipeDefensor/TiLiA.git
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

Read the CONTRIBUTING.md file at the root directory.

## License

TiLiA is licensed under the Creative Commons Attribution-ShareAlike 4.0. The complete license can be found in the LICENSE file in this directory.

## Acknowledgments

The TiLiA interface was greatly influenced by Brent Yorgason's Audio Timeliner, which can be found at https://www.singanewsong.org/audiotimeliner/. I thank the author for developing and freely distributing his software.  

