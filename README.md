Lecdown
=======

(Work in progress; proceed with caution)

Lecdown is a small script to automatically download new/updated lecture notes
from a configured course website.

Features
--------

1.  Check and download configured web pages for new/updated links
2.  Rename file with scripting
3.  Use ETag header to efficiently check for updates

Future expansion
----------------

1.  Download HTML pages as PDF

Installation
------------

Install this package:

```sh
pip3 install git+https://github.com/jasonchoimtt/lecdown
```

Install ChromeDriver:

```sh
# On Mac:
brew install chromedriver
# On Linux: I don't know...
```

Development
-----------

You can clone this repository, and install lecdown in "editable" mode:

```sh
git clone https://github.com/jasonchoimtt/lecdown
cd lecdown
pip3 install -e .
```

Now running `lecdown` will use the version in the local repo.

Usage
-----

### Basics

```sh
# This creates lecdown.json in the current directory
lecdown init

# Add a page to extract links from
lecdown add-source http://path.to/some/course/page

# Download!
lecdown

# List downloaded files
lecdown ls
```

Lecdown works by storing an index in `lecdown.json`. Currently, it ignores any
HTML links and downloads everything else. It does not scrape links of links
either. It associates the downloaded files with the origin link in
`lecdown.json`, and also uses extended file attributes (on Mac and Linux) to
keep track of file moves.

Cookie saving
-------------

Some web pages (i.e. Piazza resources) require login to be scraped. You can use
`lecdown browser` to login to that page, then save the cookie in the console.
Currently, only the link scraper (but not the file downloader) uses the saved
cookie, but it still works for Piazza.
