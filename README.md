# brd2dxf

eagle-cad board (.brd) to dxf converter

* Tested with eagle version="9.0.1" - XML-Format
* alpha-version !!!
* ugly code, one day Hack :)

## quikstart

### get code
```
git clone git@github.com:multigcs/brd2dxf.git
cd brd2dxf
pip3 install -r requirements.txt
```

### brd2dxf example
```
./bin/brd2dxf --simple eltako.brd
```
this command line will generate a dxf file named: eltako.brd.dxf

you can use the dxf file for you cnc to engrave the copper, drill holes or mill smd-masks..

## screenshots

![gcodepreview](https://raw.githubusercontent.com/multigcs/brd2dxf/main/docs/brd2dxf-1.png)
![gcodepreview](https://raw.githubusercontent.com/multigcs/brd2dxf/main/docs/brd2dxf-2.png)
![gcodepreview](https://raw.githubusercontent.com/multigcs/brd2dxf/main/docs/brd2dxf-3.png)

