# PhotoWoylie

PhotoWoylie (short woylie) is a script for organizing your photos. Woylie will be able to keep track of already imported
files and sorts them by date (year / month), location and camera.

It works best on CoW File Systems like btrfs, xfs, ocfs2 and Apples apfs. Woylie will try to use 
[reflinks](https://dev.to/robogeek/reflinks-vs-symlinks-vs-hard-links-and-how-they-can-help-machine-learning-projects-1cj4)
(or file clones) for importing photos and movies. It has been tested with apfs on macOS and btrfs on Ubuntu.

## Rationale:

Most users have already stored Photos on the disk in several locations. Often unable to identify which files have 
already been imported, copied, sorted. This also happens with photos from backups e.g. your smartphone. Woylie will 
import all files into hash-lib where files are stored by their hash digest. With this duplicate files will not be 
imported, even if they are from different locations (as long as the content hasn't been changed. Woylie will use 
reflinks for importing the files (where possible -> this will not work on Windows). Leveraging reflinks it will allow 
for more space efficient storage of all files since spaece is only used once. 

Exposing the Files again as via various folders makes it possible for any program to find and leverage the power of 
metadata

## Name Origin:

> The woylie or brush-tailed bettong (Bettongia penicillata) is an extremely rare, small marsupial, belonging to the
genus Bettongia, that is endemic to Australia.
>
> &mdash; <cite> [Woylie Article on Wikipedia](https://en.wikipedia.org/wiki/Woylie)</cite>

The name was chosen from the Endangered Species List to remind us of the fragile diversity of this planet.

## Dependencies 

Woylie uses [exiftool](https://exiftool.org/) for retrieving the exif information. I found it to be most reliable and 
it works even with `.heic` files from Apples iPhones and iPads. 

Install it on macOS via [homebrew](https://brew.sh/)
```
brew install exiftool
```
or on your linux distribution via your preferred package manager. 

## Folder Structure

woylie will maintain several folders in its base path passed by the `--base-path` argument and expose imported files 
in the directories. With a directory structure it is possible for all kinds of different software to use the contents.

Folders
 - `hash-lib` -- Folder for all files ordered after sha256 hash
 - `by-time` -- Photos linked after the Year and time
 - `by-location` -- Photos linked after Location
 - `by-camera` -- Photos sorted after the camera model.
 - `by-import` -- Photos by import run - contains the original file names
 - `log` -- Output for logfiles and the like
 - `data` -- general data needed by woylie

## Examples

```
python3 PhotoWoylie.py -b ~/my-photos -i /path/to/photos /other/path/to/photos
```