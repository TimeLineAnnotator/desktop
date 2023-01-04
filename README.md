# TiLiA

---

TiLiA (TimeLine Annotator) is an open-source, GUI-based software for producing and displaying complex annotations over video and audio files. It is a full-featured but easy to use set of tools for researchers and enthusiasts to better analyze their media of interest without needing to rely on musical scores. It is written in Python, using the Tkinter library for its GUI.

The main way in which TiLiA allows user to annotate media files is through timelines. Each one provides different tools and enables different annotations and visualizations. Currently, there are three types of timelines (hierarchy, marker, beat) but the idea is to implement many more.

Some examples of what TiLiA visualizations look like:

- Formal analysis of the Piano Sonata in C Major, K.284:
  - [First movement](https://www.timelineannotator.com/examples/mozart-k284-i)
  - [Second movement](https://www.timelineannotator.com/examples/mozart-k284-ii)
  - [Third movement](https://www.timelineannotator.com/examples/mozart-k284-iii)

## Current features
 - 3 different kinds of timelines
   - Hierarchy: nested and leveled units organized in arbitrally complex hierarchical structures
   - Marker: simple labeled markers to indicate discrete events
   - Beat: beat and measure markers with support to numbering
 - Controlling playback by clicking on timeline units
 - Multiple attributes linked to each timeline units
 - Video file support
 - Customizable metadata can be attached to files
 - Creation of unlimited number of timelines
 - Easy timeline edition during playback
 - Timelines can be temporarily hidden 
 - Audio of hierarchy unit can be exported separatedly 

## Planned features

There are many more features that I would like to implement than can be listed here. Some of the more interesting ones that ought to come relatively soon are:
- Improvements to timelines:
  - Hierarchy:
    - Support for anacrusis and elisions
    - Length, start and end also displayed in terms of beats and measures
    - Importing hierarchies from other file
  - Beat:
    - More measure information when inspecting a beat
    - Change beats in measure for multiple measures
- New kinds of timelines
  - Range: displays units with an extension, but not tied to hierarchical structures
  - Harmony: specific timeline for inserting harmonic information (chord or analytic symbols)
  - Audio wave
- TiLiA explorer: allows filtered searches through timeline components in multiple TiLiA files
- Font and GUI colors customization
- Enable video export
- Automatic cut detection for video
- Automatic beat detection for audio

## Documentation

Documentation is almost non-existent at this point. After more of the core features get implemented somw work will be put into that.

## How to contribute

Check our CONTRIBUTING.md file at the root directory.

## Website

A **very bare-bones** website is at www.timelineannotator.com. In the near future it will feature more information, documentation and examples of TiLiA usage.

## License

TiLiA is licensed under the Creative Commons Attribution-ShareAlike 4.0. The complete license can be found in the LICENSE file in this directory.

