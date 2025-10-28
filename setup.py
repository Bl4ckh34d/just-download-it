from setuptools import setup, find_packages

setup(
    name="justdownloadit",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "yt-dlp @ git+https://github.com/yt-dlp/yt-dlp.git@6d05cee4df30774ddce5c5c751fd2118f40c24fe",
        "pySmartDL>=1.3.4",
        "browser-cookie3>=0.19.1",
        "customtkinter>=5.2.1"
    ]
)
