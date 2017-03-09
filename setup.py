import os
from setuptools import setup

setup(
    name = "kvasirHGT",
    version = "v0.61",
    author = "Kevin Bonham, PhD",
    author_email = "kevbonham@gmail.com",
    description = "A package to identify HGT in bacterial genomes",
    license = "MIT",
    keywords = ["HGT", "biology", "bacteria", "genomics"],
    url = "http://github.com/kescobo/kvasir",
    download_url = 'https://github.com/kescobo/kvasir/archive/v0.61-beta.tar.gz',
    packages=['kvasir', 'tests'],
    scripts=[os.path.join('bin', 'blast.py'),
             os.path.join('bin', 'import_genomes.py')],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "License :: OSI Approved :: MIT License",
    ],
)
