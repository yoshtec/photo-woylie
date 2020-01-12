# PhotoWoylie

PhotoWoylie (short woylie) is a script for organizing your photos.

It is intended to be used with CoW File Systems like btrfs, xfs, apfs. Woylie will try to use reflinks (or file clones)
for importing photos and movies.

## Rationale:

Leveraging reflinks it will allow for more space efficient storage of the duplicated files. Most users have already
stored Photos on the disk in several locations. Often unable to identify which files have already been imported,
copied, sorted or the like. Woylie will import all files to the hash-lib where files are stored by their hash digest.
duplicate files will thus not be imported, even if they are from different locations (as long as the content hasn't
been changed.

## Name Origin:

> The woylie or brush-tailed bettong (Bettongia penicillata) is an extremely rare, small marsupial, belonging to the
genus Bettongia, that is endemic to Australia.
>
> &mdash; <cite> [Woylie Article on Wikipedia](https://en.wikipedia.org/wiki/Woylie)</cite>

The name was chosen from the Endangered Species List to remind us of the fragile diversity of this planet.

## Dependencies 

Woylie uses [exiftool](https://exiftool.org/) for retrieving the exif information. I found it to be most reliable and it works even with `.heic` 
files from Apples iPhones and iPads. 

Install it on macOS via [homebrew](https://brew.sh/)
```
brew install exiftool
```
or on your linux distribution via your preferred package manager. 

## Folder Structure

Folders
 - `hash-lib` -- Folder for all files ordered after sha256 hash
 - `by-time` -- Photos linked after the Year and time
 - `by-camera` -- Photos sorted after the camera model.
 - `by-import` -- Photos by import run - contains the original file names
 - `log` -- Output for logfiles and the like
 - `data` -- general data needed by woylie

