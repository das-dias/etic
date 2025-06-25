# `etic`

Easily download bibtex formatted citations from DOI identifier.

Heavily inspired from [citation](https://github.com/foucault/citation). I copied the project and transformed it into a pip-installable console application.

### Example Usage:
Input:
```sh
$ etic 10.1016/j.ultrasmedbio.2010.02.012
```

Console Output:
```sh
@article{Culjat2010uim&b,
 author = {Culjat, Martin O. and Goldenberg, David and Tewari, Priyamvada and Singh, Rahul S.},
 doi = {10.1016/j.ultrasmedbio.2010.02.012},
 issn = {0301-5629},
 journal = {Ultrasound in Medicine &amp; Biology},
  month = jun,
 number = {6},
 pages = {861–873},
 publisher = {Elsevier BV},
 title = {A Review of Tissue Substitutes for Ultrasound Imaging},
 url = {http://dx.doi.org/10.1016/j.ultrasmedbio.2010.02.012},
 volume = {36},
 year = {2010}
}
```

Just copy the output and save it into your `.bib` file.

### License:
MIT

### Contributing:
Please do if you feel like it! Just raise a PR.
