import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="aves",
    version="3.0.0",
    author="Sergio Oller Moreno",
    author_email="sergioller@gmail.com",
    description="Acquisition, Visualization and Exploration Software",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/zeehio/aves",
    packages=setuptools.find_packages(),
    install_requires=[
          'pyserial',
          'matplotlib',
      ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)

