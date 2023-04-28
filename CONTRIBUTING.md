Thank you for considering contributing to TiLiA! I really believe that, with the help of an active community, this software might significantly change the way we study, understand and write about music, cinema and other topics related to audio and video.

# Where to contribute
In this early stage, the contributing process is not really structured, and help is needed is almost every front. Feel free to make PR or to contact me to discuss contributing.

Some of the issues where contributions would be most appreciated:

## Testing:
Somewhat thorough tests have been written the timeline's logic, but the UI has very little in terms of tests. That is mainly to the difficulty of testing tkinter UI's and the possibility of changing the engine to PyQt in the future. However, there are many UI features that could be tested without relying too heavily on tkinter. The current test coverage could probably be greatly improved.

## Tutorials/guides:
The program should be fairly intuitive for the users, but tutorials and guides will need to be done at some point, as they will significantly facilitate the adoption by new users. They can be either written or in video form, ideally both. [This video](https://vimeo.com/767282249) serves as rough general quickstart guide, for now.

## Documentation:
The documentation is almost non-existent at the moment. Docstrings for functions and modules need to start being inserted soon.

## New features
If you think about a valuable feature that would be easy to implement, don't hesitate to make a PR.

## Making TiLiA analyses
With the new platform in the making (https://tilia-ad98d.web.app/), it is possible to share TiLiA files publicly. Increasing the amount of available files would be of great help.

## Reporting bugs
If you find a bug, [check](https://github.com/FelipeDefensor/TiLiA/issues) if there isn't an open issue reporting it, if not, please [open a new one](https://github.com/FelipeDefensor/TiLiA/issues/new). The following information might be helpful:

- Your operating system;
- TiLiA version (can be found in the Help > About menu);
- Description of the issue;
- Steps to reproduce it.

# Suggesting features or enchancements

We are very much looking for ideas of new features for TiLiA. If you would like to suggest one, [check](https://github.com/FelipeDefensor/TiLiA/issues) if there isn't an issue requesting. If not, [open a new one](https://github.com/FelipeDefensor/TiLiA/issues/new) detailing your suggestion.

TiLiA was tested using Python 3.10. You will also need to have ffmpeg installed to use the export and convert audio features. [VLC player](https://www.videolan.org/) is needed for video playback.

<<<<<<< HEAD
Be sure that your code:
- Uses type hints for all parameters of functions;
- Is formatted using [black](https://github.com/psf/black);

<<<<<<< HEAD
TiLiA was tested using Python 3.11.1. You will also need to have ffmpeg installed to use the export and convert audio features. [VLC player](https://www.videolan.org/) is needed for video playback.

=======
TiLiA was tested using Python 3.11.1. You will also need to have ffmpeg installed to use the export and convert audio features. [VLC player](https://www.videolan.org/) is needed for video playback. 
 
>>>>>>> a96bc09 (improved phrasing)
=======
>>>>>>> 1030956 (Update CONTRIBUTING.md)
If you need any help getting around the repository (you probably will, given its current state) don't hesitate to e-mail me at felipe.martins4@hotmail.com.
