import setuptools

with open("readme.md", "r") as fh:
    long_description = fh.read()

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setuptools.setup(
    author="Richard Dally",
    name="rtube",
    version="1.0.0",
    description="Streaming platform from scratch",
    url="https://github.com/RichardDally/RTube",
    license="MIT License",
    install_requires=requirements,
    packages=setuptools.find_packages(),
    author_email="r.dally@pm.me",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
