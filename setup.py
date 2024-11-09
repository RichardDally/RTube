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
    include_package_data=True,
    zip_safe=False,
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires='>=3.11',
)
