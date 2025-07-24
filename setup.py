from setuptools import setup, find_packages

setup(
    name="justdownloadit",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "yt-dlp>=2025.07.21",
        "pySmartDL>=1.3.4",
        "browser-cookie3>=0.19.1",
        "customtkinter>=5.2.1"
    ]
)
