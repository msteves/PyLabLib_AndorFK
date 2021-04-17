"""
PyQtGraph-based image plotter.

Includes additional extensions: pair of lines to extract coordinates, line cuts, settings/getting limits numerically, etc.

Has 2 parts: :class:`ImagePlotter` which displays the image,
and :class:`ImagePlotterCtl` which controls the image display (value ranges, flipping or transposing, etc.)
:class:`ImagePlotter` can also operate alone without a controller.
When both are used, :class:`ImagePlotter` is created and set up first, and then supplied to :meth:`ImagePlotterCtl.setupUi` method.
"""

from ....core.gui.widgets.param_table import ParamTable
from ....core.gui.value_handling import create_virtual_values
from ....core.thread import controller
from ....core.utils import funcargparse, module, dictionary
from ....core.dataproc import filters

import pyqtgraph

from ....core.gui import QtWidgets, QtCore
import numpy as np
import contextlib
import time

_pre_0p11=module.cmp_package_version("pyqtgraph","0.11.0")=="<"







class ImagePlotterCtl(QtWidgets.QWidget):
    """
    Class for controlling an image inside :class:`ImagePlotter`.

    Like most widgets, requires calling :meth:`setupUi` to set up before usage.

    Args:
        parent: parent widget
    """
    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(parent)

    def setupUi(self, name, plotter, gui_values=None, gui_values_root=None, save_values=("colormap","img_lim_preset")):
        """
        Setup the image plotter controller.

        Args:
            name (str): widget name
            plotter (ImagePlotter): controlled image plotter
            gui_values (bool): as :class:`.GUIValues` object used to access table values; by default, create one internally
            gui_values_root (str): if not ``None``, specify root (i.e., path prefix) for values inside the table.
            save_values (tuple): optional parameters to include on :meth:`get_all_values`;
                can include ``"colormap"`` (colormap defined in the widget), and ``"img_lim_preset"`` (saved image limit preset)
        """
        self.name=name
        self.save_values=save_values
        self.setObjectName(self.name)
        self.hLayout=QtWidgets.QHBoxLayout(self)
        self.hLayout.setContentsMargins(0,0,0,0)
        self.hLayout.setObjectName("hLayout")
        self.plotter=plotter
        self.plotter._attach_controller(self)
        self.settings_table=ParamTable(self)
        self.settings_table.setObjectName("settings_table")
        self.hLayout.addWidget(self.settings_table)
        self.img_lim=(0,65536)
        self.settings_table.setupUi("img_settings",add_indicator=False,gui_values=gui_values,gui_values_root=gui_values_root)
        self.settings_table.add_text_label("size",label="Image size:")
        self.settings_table.add_check_box("flip_x","Flip X",value=False)
        self.settings_table.add_check_box("flip_y","Flip Y",value=False,location=(-1,1))
        self.settings_table.add_check_box("transpose","Transpose",value=True)
        self.settings_table.add_check_box("normalize","Normalize",value=False)
        self.settings_table.add_num_edit("minlim",value=self.img_lim[0],limiter=self.img_lim+("coerce","int"),formatter=("int"),label="Minimal intensity:",add_indicator=True)
        self.settings_table.add_num_edit("maxlim",value=self.img_lim[1],limiter=self.img_lim+("coerce","int"),formatter=("int"),label="Maximal intensity:",add_indicator=True)
        self._preset_layout=QtWidgets.QHBoxLayout()
        row_loc=self.settings_table._normalize_location((None,0,1,self.settings_table.layout().columnCount()))
        self.settings_table.layout().addLayout(self._preset_layout,*row_loc)
        hbtn=self.settings_table.add_button("save_preset","Save preset")
        hbtn.value_changed().connect(self._save_img_lim_preset)
        self._preset_layout.addWidget(hbtn.widget)
        hbtn=self.settings_table.add_button("load_preset","Load preset")
        hbtn.value_changed().connect(self._load_img_lim_preset)
        self._preset_layout.addWidget(hbtn.widget)
        self.img_lim_preset=self.img_lim
        self.settings_table.add_check_box("show_histogram","Show histogram",value=True).value_changed().connect(self._setup_gui_state)
        self.settings_table.add_check_box("auto_histogram_range","Auto histogram range",value=True)
        self.settings_table.add_check_box("show_lines","Show lines",value=True).value_changed().connect(self._setup_gui_state)
        self.settings_table.add_num_edit("vlinepos",value=0,limiter=(0,None,"coerce","float"),formatter=("float","auto",1,True),label="X line:")
        self.settings_table.add_num_edit("hlinepos",value=0,limiter=(0,None,"coerce","float"),formatter=("float","auto",1,True),label="Y line:")
        self.settings_table.add_check_box("show_linecuts","Show line cuts",value=False).value_changed().connect(self._setup_gui_state)
        self.settings_table.add_num_edit("linecut_width",value=1,limiter=(1,None,"coerce","int"),formatter="int",label="Line cut width:")
        self.settings_table.add_button("center_lines","Center lines").value_changed().connect(plotter.center_lines)
        self.settings_table.value_changed.connect(lambda n: self.plotter.update_image(update_controls=(n=="normalize"),do_redraw=True),QtCore.Qt.DirectConnection)
        self.settings_table.add_spacer(10)
        self.settings_table.add_toggle_button("update_image","Updating").value_changed().connect(plotter._set_image_update)
        def arm_single():
            self.settings_table.v["update_image"]=False
            self.plotter.arm_single()
        self.settings_table.add_button("single","Single").value_changed().connect(arm_single)
        self.settings_table.add_padding()

    def set_img_lim(self, *args):
        """
        Set up image value limits.

        Specifies the minimal and maximal values in ``Minimal intensity`` and ``Maximal intensity`` controls.
        Can specify either only upper limit (lower stays the same), or both limits.
        Value of ``None`` implies no limit.
        """
        if len(args)==1:
            self.img_lim=(self.img_lim[0],args[0])
        elif len(args)==2:
            self.img_lim=tuple(args)
        else:
            return
        minl,maxl=self.img_lim
        self.settings_table.w["minlim"].set_number_limit(minl,maxl,"coerce","int")
        self.settings_table.w["maxlim"].set_number_limit(minl,maxl,"coerce","int")
    @controller.exsafeSlot()
    def _save_img_lim_preset(self):
        self.img_lim_preset=self.settings_table.v["minlim"],self.settings_table.v["maxlim"]
    @controller.exsafeSlot()
    def _load_img_lim_preset(self):
        self.settings_table.v["minlim"],self.settings_table.v["maxlim"]=self.img_lim_preset
    @controller.exsafeSlot()
    def _setup_gui_state(self):
        """Enable or disable controls based on which actions are enabled"""
        show_histogram=self.settings_table.v["show_histogram"]
        self.settings_table.lock("auto_histogram_range",not show_histogram)
        show_lines=self.settings_table.v["show_lines"]
        for n in ["vlinepos","hlinepos","show_linecuts"]:
            self.settings_table.lock(n,not show_lines)
        show_linecuts=self.settings_table.v["show_linecuts"]
        self.settings_table.lock("linecut_width",not (show_lines and show_linecuts))

    def get_all_values(self):
        """Get all control values"""
        values=self.settings_table.get_all_values()
        if "img_lim_preset" in self.save_values:
            values["img_lim_preset"]=self.img_lim_preset
        if "colormap" in self.save_values:
            values["colormap"]=self.plotter.imageWindow.getHistogramWidget().gradient.saveState()
        return values
    def set_all_values(self, values):
        """Set all control values"""
        self.settings_table.set_all_values(values)
        if "img_lim_preset" in values:
            self.img_lim_preset=values["img_lim_preset"]
        if "colormap" in values:
            colormap=dictionary.as_dict(values["colormap"],style="nested")
            self.plotter.imageWindow.getHistogramWidget().gradient.restoreState(colormap)
        self._setup_gui_state()
    def get_all_indicators(self):
        """Get all GUI indicators as a dictionary"""
        return self.settings_table.get_all_indicators()







class ImageItem(pyqtgraph.ImageItem):
    """Minor extension of :class:`pyqtgraph.ImageItem` which keeps track of painting events (last time and number of calls)"""
    def __init__(self, *args, **kwargs):
        pyqtgraph.ImageItem.__init__(self,*args,**kwargs)
        self.paint_cnt=0
        self.paint_time=None
    def paint(self, *args):
        pyqtgraph.ImageItem.paint(self,*args)
        self.paint_time=time.time()
        self.paint_cnt+=1

class PlotCurveItem(pyqtgraph.PlotCurveItem):
    """Minor extension of :class:`pyqtgraph.PlotCurveItem` which keeps track of painting events (last time and number of calls)"""
    def __init__(self, *args, **kwargs):
        pyqtgraph.PlotCurveItem.__init__(self,*args,**kwargs)
        self.paint_cnt=0
        self.paint_time=None
    def paint(self, *args):
        pyqtgraph.PlotCurveItem.paint(self,*args)
        self.paint_time=time.time()
        self.paint_cnt+=1


builtin_cmaps={ "gray":([0,1.],[(0.,0.,0.),(1.,1.,1.)]),
                "gray_sat":([0,0.99,1.],[(0.,0.,0.),(1.,1.,1.),(1.,0.,0.)]),
                "hot":([0,0.3,0.7,1.],[(0.,0.,0.),(1.,0.,0.),(1.,1.,0.),(1.,1.,1.)]),
                "hot_sat":([0,0.3,0.7,0.99,1.],[(0.,0.,0.),(1.,0.,0.),(1.,1.,0.),(1.,1.,1.),(0.,0.,1.)])
            }
for cm in ["hot_sat","hot"]: # add custom cmaps to pyqtgraph widgets
    ticks=[(p,(int(r*255),int(g*255),int(b*255),255)) for p,(r,g,b) in zip(*builtin_cmaps[cm])]
    pyqtgraph.graphicsItems.GradientEditorItem.Gradients[cm]={"ticks":ticks,"mode":"rgb"}
class ImagePlotter(QtWidgets.QWidget):
    """
    Image plotter object.

    Built on top of :class:`pyqtgraph.ImageView` class.

    Args:
        parent: parent widget
    """
    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(parent)
        self.ctl=None

    class Rectangle(object):
        def __init__(self, rect, center=None, size=None):
            object.__init__(self)
            self.rect=rect
            self.center=center or (0,0)
            self.size=size or (0,0)
        def update_parameters(self, center=None, size=None):
            if center:
                self.center=center
            if size:
                self.size=size
    def setupUi(self, name, img_size=(1024,1024), min_size=None):
        """
        Setup the image plotter.

        Args:
            name (str): widget name
            img_size (tuple): default image size (used only until actual image is supplied)
            min_size (tuple): minimal widget size (``None`` mean no minimal size)
        """
        self.name=name
        self.setObjectName(self.name)
        self.single_armed=False
        self.single_acquired=False
        self.hLayout=QtWidgets.QVBoxLayout(self)
        self.hLayout.setContentsMargins(0,0,0,0)
        self.hLayout.setObjectName(self.name+"hLayout")
        self.img=np.zeros(img_size)
        self.do_image_update=False
        self.xbin=1
        self.ybin=1
        self.dec_mode="mean"
        self._updating_image=False
        self._last_paint_time=None
        self._last_img_paint_cnt=None
        self._last_curve_paint_cnt=[None,None]
        if min_size:
            self.setMinimumSize(QtCore.QSize(*min_size))
        self.imageWindow=pyqtgraph.ImageView(self,imageItem=ImageItem())
        self.imageWindow.setObjectName("imageWindow")
        self.hLayout.addWidget(self.imageWindow)
        self.hLayout.setStretch(0,4)
        self.set_colormap("hot_sat")
        self.imageWindow.ui.roiBtn.hide()
        self.imageWindow.ui.menuBtn.hide()
        self.imageWindow.getView().setMenuEnabled(False)
        self.imageWindow.getView().setMouseEnabled(x=False,y=False)
        self.imageWindow.getHistogramWidget().item.vb.setMenuEnabled(False)
        self.imgVLine=pyqtgraph.InfiniteLine(angle=90,movable=True,bounds=[0,None])
        self.imgHLine=pyqtgraph.InfiniteLine(angle=0,movable=True,bounds=[0,None])
        self.imageWindow.getView().addItem(self.imgVLine)
        self.imageWindow.getView().addItem(self.imgHLine)
        self.linecut_boundary_pen=pyqtgraph.mkPen("#008000",style=pyqtgraph.QtCore.Qt.DashLine)
        self.imgHBLines=[pyqtgraph.InfiniteLine(angle=0,movable=False,bounds=[0,None],pen=self.linecut_boundary_pen) for _ in range(2)]
        self.imgVBLines=[pyqtgraph.InfiniteLine(angle=90,movable=False,bounds=[0,None],pen=self.linecut_boundary_pen) for _ in range(2)]
        self.imageWindow.getView().addItem(self.imgHBLines[0])
        self.imageWindow.getView().addItem(self.imgHBLines[1])
        self.imageWindow.getView().addItem(self.imgVBLines[0])
        self.imageWindow.getView().addItem(self.imgVBLines[1])
        self.plotWindow=pyqtgraph.PlotWidget(self)
        self.plotWindow.addLegend()
        self.plotWindow.setLabel("left","Image cut")
        self.plotWindow.showGrid(True,True,0.7)
        self.cut_lines=[PlotCurveItem(pen="#B0B000",name="Horizontal"), PlotCurveItem(pen="#B000B0",name="Vertical")]
        for c in self.cut_lines:
            self.plotWindow.addItem(c)
        self.hLayout.addWidget(self.plotWindow)
        self.hLayout.setStretch(1,1)
        self.plotWindow.setVisible(False)
        self.imgVLine.sigPositionChanged.connect(self.update_image_controls,QtCore.Qt.DirectConnection)
        self.imgHLine.sigPositionChanged.connect(self.update_image_controls,QtCore.Qt.DirectConnection)
        self.imageWindow.getHistogramWidget().sigLevelsChanged.connect(lambda: self.update_image_controls(levels=self.imageWindow.getHistogramWidget().getLevels()),QtCore.Qt.DirectConnection)
        self.rectangles={}

    def _attach_controller(self, ctl):
        """
        Attach :class:`ImagePlotterCtl` object.

        Called automatically in :meth:`ImagePlotterCtl.setupUi`
        """
        self.ctl=ctl
    def _get_values(self):
        if self.ctl is not None:
            return self.ctl.settings_table
        return create_virtual_values(**{"transpose":False,
                "flip_x":False,
                "flip_y":False,
                "normalize":True,
                "show_lines":False,
                "show_histogram":True,
                "auto_histogram_range":True,
                "show_linecuts":False,
                "vlinepos":0,
                "hlinepos":0,
                "linecut_width":0,
                "update_image":True})
    @controller.exsafeSlot("bool")
    def _set_image_update(self, do_update):
        self.do_image_update=do_update
    
    @contextlib.contextmanager
    def _while_updating(self, updating=True):
        curr_updating=self._updating_image
        self._updating_image=updating
        try:
            yield
        finally:
            self._updating_image=curr_updating

    def set_colormap(self, cmap):
        """
        Setup colormap.

        Can be name of one built-in colormaps (``"gray"``, ``"gray_sat"``, ``"hot"``, ``"hot_sat"``),
        one of PyQtGraph built-in cmaps (e.g., ``"flame"`` or ``"bipolar"``),
        a list specifying PyQtGraph colormap or a :class:`pyqtgraph.ColorMap` instance.
        """
        if cmap in pyqtgraph.graphicsItems.GradientEditorItem.Gradients:
            self.imageWindow.setPredefinedGradient(cmap)
        else:
            cmap=builtin_cmaps.get(cmap,cmap)
            if isinstance(cmap,tuple):
                if any([isinstance(v,float) for c in cmap[1] for v in c]):
                    cols=[tuple([int(v*255) for v in c]) for c in cmap[1]]
                    cmap=cmap[0],cols
                cmap=pyqtgraph.ColorMap(*cmap)
            self.imageWindow.setColorMap(cmap)
    def set_binning(self, xbin=1, ybin=1, mode="mean", update_image=True):
        """
        Set image binning (useful for showing large images).
        """
        bin_changes=(xbin!=self.xbin) or (ybin!=self.ybin) or (mode!=self.dec_mode)
        self.xbin=xbin
        self.ybin=ybin
        self.dec_mode=mode
        if bin_changes and update_image:
            self.update_image(update_controls=True,do_redraw=True)
    def set_image(self, img):
        """
        Set the current image.

        The image display won't be updated until :meth:`update_image` is called.
        This function is thread-safe (i.e., the application state remains consistent if it's called from another thread,
        although race conditions on simultaneous calls from multiple threads still might happen).
        """
        if self.do_image_update or self.single_armed:
            self.img=img
            self.single_armed=False
            self.single_acquired=True
    def arm_single(self):
        """Arm the single-image trigger"""
        self.single_armed=True

    def _show_histogram(self, show=True):
        if show:
            self.imageWindow.ui.histogram.show()
        else:
            self.imageWindow.ui.histogram.hide()
    def set_rectangle(self, name, center=None, size=None):
        """
        Add or change parameters of a rectangle with a given name.

        Rectangle coordinates are specified in the original image coordinate system
        (i.e., rectangles are automatically flipped/transposed/scaled with the image).
        """
        if name not in self.rectangles:
            pqrect=pyqtgraph.ROI((0,0),(0,0),movable=False,pen="#FF00FF")
            self.imageWindow.getView().addItem(pqrect)
            self.rectangles[name]=self.Rectangle(pqrect)
        rect=self.rectangles[name]
        rect.update_parameters(center,size)
        rcenter=rect.center[0]-rect.size[0]/2.,rect.center[1]-rect.size[1]/2.
        rsize=rect.size
        imshape=self.img.shape
        values=self._get_values()
        rcenter=rcenter[0]/self.xbin,rcenter[1]/self.ybin
        rsize=rsize[0]/self.xbin,rsize[1]/self.ybin
        if values.v["transpose"]:
            rcenter=rcenter[::-1]
            rsize=rsize[::-1]
            imshape=imshape[::-1]
        if values.v["flip_x"]:
            rcenter=(imshape[0]-rcenter[0]-rsize[0]),rcenter[1]
        if values.v["flip_y"]:
            rcenter=rcenter[0],(imshape[1]-rcenter[1]-rsize[1])
        rect.rect.setPos(rcenter)
        rect.rect.setSize(rsize)
    def update_rectangles(self):
        """Update rectangle coordinates"""
        for name in self.rectangles:
            self.set_rectangle(name)
    def del_rectangle(self, name):
        """Delete a rectangle with a given name"""
        if name in self.rectangles:
            rect=self.rectangles.pop(name)
            self.imageWindow.getView().removeItem(rect)
    def show_rectangles(self, show=True, names=None):
        """
        Toggle showing rectangles on or off
        
        If `names` is given, it specifies names of rectangles to show or hide (by default, all rectangles).
        """
        imgview=self.imageWindow.getView()
        if names is None:
            names=self.rectangles
        else:
            names=funcargparse.as_sequence(names)
        for n in names:
            rect=self.rectangles[n]
            if show and rect.rect not in imgview.addedItems:
                imgview.addItem(rect.rect)
            if (not show) and rect.rect in imgview.addedItems:
                imgview.removeItem(rect.rect)

    @controller.exsafe
    def center_lines(self):
        """Center coordinate lines"""
        imshape=self.img.shape[::-1] if self._get_values().v["transpose"] else self.img.shape
        self.imgVLine.setPos(imshape[0]/2)
        self.imgHLine.setPos(imshape[1]/2)
    def _update_linecut_boundaries(self, values):
        vpos=self.imgVLine.getPos()[0]
        hpos=self.imgHLine.getPos()[1]
        cut_width=values.v["linecut_width"]
        show_boundary_lines=values.v["show_lines"] and values.v["show_linecuts"] and cut_width>1
        for ln in self.imgVBLines+self.imgHBLines:
            ln.setPen(self.linecut_boundary_pen if show_boundary_lines else None)
        if show_boundary_lines:
            self.imgVBLines[0].setPos(vpos-cut_width/2)
            self.imgVBLines[1].setPos(vpos+cut_width/2)
            self.imgHBLines[0].setPos(hpos-cut_width/2)
            self.imgHBLines[1].setPos(hpos+cut_width/2)

    # Update image controls based on PyQtGraph image window
    @controller.exsafeSlot()
    def update_image_controls(self, levels=None):
        """Update image controls in the connected :class:`ImagePlotterCtl` object"""
        if self._updating_image:
            return
        values=self._get_values()
        if levels is not None:
            values.v["minlim"],values.v["maxlim"]=levels
        values.v["vlinepos"]=self.imgVLine.getPos()[0]
        values.v["hlinepos"]=self.imgHLine.getPos()[1]
        self._update_linecut_boundaries(values)
    def _get_min_nonzero(self, img, default=0):
        img=img[img!=0]
        return default if np.all(np.isnan(img)) else np.nanmin(img)
    def _sanitize_img(self, img): # PyQtGraph histogram has an unfortunate failure mode (crashing) when the image is integer and is constant
        """Correct the image so that it doesn't cause crashes on pyqtgraph 0.10.0"""
        if not _pre_0p11:
            return img
        if np.prod(img.shape)<=1: # empty or single-pixel image
            img=np.zeros((2,2),dtype=img.dtype)+(img[0,0] if np.prod(img.shape) else 0)
        step=int(np.ceil(img.shape[0]/200)),int(np.ceil(img.shape[1]/200))
        stepData=img[::step[0],::step[1]]
        if stepData.dtype.kind in "ui" and stepData.min()==stepData.max():
            img=img.copy()
            img[0,0]+=1
        return img
    def _check_paint_done(self, dt=0):
        items=[self.imageWindow.imageItem]+self.cut_lines
        counters=[self._last_img_paint_cnt]+self._last_curve_paint_cnt
        if self._last_img_paint_cnt==self.imageWindow.imageItem.paint_cnt:
            return False
        for itm,cnt in zip(items,counters):
            if itm.paint_cnt==cnt:
                return False
        t=time.time()
        passed_time=min([t-(itm.paint_time or 0) for itm in items])
        if passed_time<dt:
            return False
        return True
    # Update image plot
    @controller.exsafe
    def update_image(self, update_controls=False, do_redraw=False, only_new_image=True):
        """
        Update displayed image.

        If ``update_controls==True``, update control values (such as image min/max values and line positions).
        If ``do_redraw==True``, force update regardless of the ``"update_image"`` button state; otherwise, update only if it is enabled.
        If ``only_new_image==True`` and the image hasn't changed since the last call to ``update_image``, skip redraw (however, if ``do_redraw==True``, force redrawing regardless).
        """
        if self._updating_image:
            return
        dt=min(time.time()-self._last_paint_time,0.1) if self._last_paint_time else 0.1
        if not self._check_paint_done(dt*0.1):
            return
        with self._while_updating():
            values=self._get_values()
            if not do_redraw:
                if not (values.v["update_image"] or self.single_acquired):
                    return
                if only_new_image and not self.single_acquired:
                    return
                self.single_acquired=False
            draw_img=self.img
            if self.xbin>1:
                draw_img=filters.decimate(draw_img,self.xbin,dec_mode=self.dec_mode,axis=0)
            if self.ybin>1:
                draw_img=filters.decimate(draw_img,self.ybin,dec_mode=self.dec_mode,axis=1)
            if values.v["transpose"]:
                draw_img=draw_img.transpose()
            if values.v["flip_x"]:
                draw_img=draw_img[::-1,:]
            if values.v["flip_y"]:
                draw_img=draw_img[:,::-1]
            img_shape=draw_img.shape
            autoscale=values.v["normalize"]
            all_nan=np.all(np.isnan(draw_img))
            img_levels=[0,1] if all_nan else (np.nanmin(draw_img),np.nanmax(draw_img))
            draw_img=self._sanitize_img(draw_img)
            levels=img_levels if autoscale else (values.v["minlim"],values.v["maxlim"])
            if self.isVisible():
                self.imageWindow.setImage(draw_img,levels=levels,autoHistogramRange=False)
                if values.v["auto_histogram_range"]:
                    hist_range=min(img_levels[0],levels[0]),max(img_levels[1],levels[1])
                    if hist_range[0]==hist_range[1]:
                        hist_range=hist_range[0]-.5,hist_range[1]+.5
                    self.imageWindow.ui.histogram.setHistogramRange(*hist_range)
                self._last_img_paint_cnt=self.imageWindow.imageItem.paint_cnt
            if update_controls:
                with self._while_updating(False):
                    self.update_image_controls(levels=levels if autoscale else None)
            self._show_histogram(values.v["show_histogram"])
            values.i["minlim"]=img_levels[0]
            values.i["maxlim"]=img_levels[1]
            values.v["size"]="{} x {}".format(*img_shape)
            show_lines=values.v["show_lines"]
            for ln in [self.imgVLine,self.imgHLine]:
                ln.setPen("g" if show_lines else None)
                ln.setHoverPen("y" if show_lines else None)
                ln.setMovable(show_lines)
            for ln in [self.imgVLine]+self.imgVBLines:
                ln.setBounds([0,draw_img.shape[0]])
            for ln in [self.imgHLine]+self.imgHBLines:
                ln.setBounds([0,draw_img.shape[1]])
            self.imgVLine.setPos(values.v["vlinepos"])
            self.imgHLine.setPos(values.v["hlinepos"])
            self._update_linecut_boundaries(values)
            if values.v["show_lines"] and values.v["show_linecuts"]:
                cut_width=values.v["linecut_width"]
                vpos=values.v["vlinepos"]
                vmin=int(min(max(0,vpos-cut_width/2),draw_img.shape[0]-1))
                vmax=int(vpos+cut_width/2)
                if vmax==vmin:
                    if vmin==0:
                        vmax+=1
                    else:
                        vmin-=1
                hpos=values.v["hlinepos"]
                hmin=int(min(max(0,hpos-cut_width/2),draw_img.shape[1]-1))
                hmax=int(hpos+cut_width/2)
                if hmax==hmin:
                    if hmin==0:
                        hmax+=1
                    else:
                        hmin-=1
                x_cut=draw_img[:,hmin:hmax].mean(axis=1)
                y_cut=draw_img[vmin:vmax,:].mean(axis=0)
                autorange=self.plotWindow.getViewBox().autoRangeEnabled()
                self.plotWindow.disableAutoRange()
                self.cut_lines[0].setData(np.arange(len(x_cut)),x_cut)
                self.cut_lines[1].setData(np.arange(len(y_cut)),y_cut)
                self._last_img_paint_cnt=[cl.paint_cnt for cl in self.cut_lines]
                if any(autorange):
                    self.plotWindow.enableAutoRange(x=autorange[0],y=autorange[1])
                self.plotWindow.setVisible(True)
            else:
                self.plotWindow.setVisible(False)
            self.update_rectangles()
            self._last_paint_time=time.time()
            return values