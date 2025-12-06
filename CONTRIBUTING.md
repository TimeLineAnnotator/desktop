Thank you for contributing to TiLiA! We believe that, with the help of an active community, this software will significantly change the way we study, understand and write about music, film and other topics related to audio and video.

# Where to contribute
Help is appreciated is every front. Feel free to make PR or to get in touch to discuss your contribution.

Apart from coding proper, contributions would be appreciated in:

## Automated testing
Testing guidelines can be found [here](./TESTING.md).

## Tutorials/guides:
The program should be fairly intuitive for users, but comprehensive tutorials and guides will need to be done at some point, as they will significantly facilitate the adoption of this program by new users. They can be either written or in video form, ideally both. [This video](https://vimeo.com/767282249) serves as rough general quickstart guide, for now.

## Documentation:
The documentation is almost non-existent at the moment. Docstrings for functions and modules need to be inserted soon.

## Making annotations using TiLiA
With the new platform in the making (https://tilia-app.com/), it is possible to share TiLiA files publicly. Increasing the number of available files would be of great help.

## Reporting bugs
If you find a bug, [check](https://github.com/TimeLineAnnotator/desktop/issues) if there is already an open issue reporting it. If not, please [open a new one](https://github.com/TimeLineAnnotator/desktop/issues/new). The following information in  your report will be greatly appreciated:

- Your operating system;
- TiLiA version (can be found in the Help > About menu);
- Description of the issue;
- Steps to reproduce it.

# Suggesting features or enhancements
We are very much looking for ideas of new features for TiLiA. If you would like to suggest one, [check](https://github.com/TimeLineAnnotator/desktop/issues) to see if your feature has already been requested. If not, [open a new one](https://github.com/TimeLineAnnotator/desktop/issues/new) detailing your suggestion.

You need Python >=3.10 to build and test TiLiA. You will also need to have ffmpeg installed to use the export and convert audio features.

# Developing for TiLiA
For a better development experience, we recommend the installation of a few more packages:
```
pip install --group dev --group testing
pre-commit install
```
