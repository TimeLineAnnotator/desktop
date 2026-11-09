Thank you for contributing to TiLiA! We believe that, with the help of an active community, this software will significantly change the way we study, understand and write about music, film and other topics related to audio and video.

# Where to contribute
Help is appreciated is every front. Feel free to make PR or to get in touch to discuss your contribution.

Apart from coding proper, contributions would be appreciated in:

## Automated testing
Testing guidelines can be found [here](./TESTING.md).

## Tutorials/guides:
Written [guides](https://tilia-app.com/help/) and [video tutorials](https://www.youtube.com/@tilia-app) are available, and more are always useful. If you find something missing or unclear, please [open an issue](https://github.com/TimeLineAnnotator/desktop/issues/new).

## Documentation:
User documentation is available on our [help pages](https://tilia-app.com/help/). Developer documentation is still sparse: few functions and modules have docstrings, so contributions there are welcome.

## Making annotations using TiLiA
Our [online platform](https://tilia-app.com/) makes it possible to share TiLiA files publicly. Increasing the number of available files would be of great help.

## Reporting bugs
If you find a bug, [check](https://github.com/TimeLineAnnotator/desktop/issues) if there is already an open issue reporting it. If not, please [open a new one](https://github.com/TimeLineAnnotator/desktop/issues/new). The following information in  your report will be greatly appreciated:

- Your operating system;
- TiLiA version (can be found in the Help > About menu);
- Description of the issue;
- Steps to reproduce it.

# Suggesting features or enhancements
We are very much looking for ideas of new features for TiLiA. If you would like to suggest one, [check](https://github.com/TimeLineAnnotator/desktop/issues) to see if your feature has already been requested. If not, [open a new one](https://github.com/TimeLineAnnotator/desktop/issues/new) detailing your suggestion.

You need Python 3.12–3.14 to build and test TiLiA. You will also need to have ffmpeg installed to use the export and convert audio features.

# AI tools and agents
You may use AI tools to contribute to TiLiA, on two conditions:

- **Disclose it.** If an AI tool wrote any of the code, tests or text of a pull request, say so in its description, and name the tool. The same goes for issues and comments.
- **No purely autonomous agents.** Every pull request needs a person behind it, who asked for the change, checks it and answers for it in review. We don't accept pull requests from agents that choose issues and open pull requests on their own, and we close them without review.

# Developing for TiLiA
For a better development experience, we recommend the installation of a few more packages:
```
pip install --group dev
pre-commit install
```
