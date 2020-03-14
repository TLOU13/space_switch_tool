"""
MODULE: space_switch_tool

CLASSES:
    SpaceSwitchTool: class for main UI and space switch methods.
"""
import shiboken2 as shiboken
from functools import partial

import maya.mel as mel
import maya.cmds as cmds
import maya.OpenMayaUI as OpenMayaUI
from PySide2 import QtWidgets, QtGui, QtCore


def lock_viewport():
    """ Find Maya viewport and lock it down to save feedback time

    This function query user's active current panel and lock it down
    if it is a modelPanel (viewport).

    """
    if not cmds.about(query=True, batch=True): # not in batch mode
        for pnl in cmds.lsUI(panels=True):
            ctrl = cmds.panel(pnl, query=True, control=True)
            if ctrl:
                if cmds.getPanel(typeOf=pnl) == 'modelPanel': # viewport
                    cmds.control(ctrl, edit=True, manage=False)
                 
def unlock_viewport():
    """ Find Maya viewport and unlock it

    This function query user's active current panel and unlock it. 
    It is a clean-up function for lock_viewport function.

    """
    if not cmds.about(query=True, batch=True): # not in batch mode
        for pnl in cmds.lsUI(panels=True):
            ctrl = cmds.panel(pnl, query=True, control=True)
            if ctrl:
                if cmds.getPanel(typeOf=pnl) == 'modelPanel': # viewport
                    cmds.control(ctrl, edit=True, manage=True)

def filter_invalid_objects(objects):
    """ Take any list and filter out None and non-existing nodes

    This function takes an object list and check if None is inside
    (result of functions like cmds.keyframe). Then it checks if the objects
    exist in the scene and returns them if they do.

    Arguments:
        objects (list): a list of any nodes.

    Returns:
        objs (list): a list of nodes that is not None and exists in Maya.

    """
    objs = []
    if objects:
        for loop_obj in objects:
            if loop_obj:
                if cmds.objExists(loop_obj):
                    objs.append(loop_obj)
                
    return objs

def create_transform_keys(objects=None, time=None, tx=False, ty=False, tz=False,
                                                 rx=False, ry=False, rz=False,
                                                 sx=False, sy=False, sz=False):
    """ Key the transform channels selectively based on flags given

    This function takes an object list and set keys on the transform channels
    based on the flags given. It is primary used to deal with cmds.setKeyframe
    function so we can avoid repeating string formatting.

    Arguments:
        objects (list): a list of any transform nodes.
        time (int or float): frame number to set key frame on, set on
                             current frame if None given.
        tx (bool): translate X channel, keyed if set to True.
        ty (bool): translate Y channel, keyed if set to True.
        tz (bool): translate Z channel, keyed if set to True.
        rx (bool): rotate X channel, keyed if set to True.
        ry (bool): rotate Y channel, keyed if set to True.
        rz (bool): rotate Z channel, keyed if set to True.
        sx (bool): scale X channel, keyed if set to True.
        sy (bool): scale Y channel, keyed if set to True.
        sz (bool): scale Z channel, keyed if set to True.

    """                
    objs = filter_invalid_objects(objects) or cmds.ls(sl=True)
    time = time or cmds.currentTime(query=True)
    attrDict = {"translateX":tx, "translateY":ty, "translateZ":tz,
                "rotateX":rx, "rotateY":ry, "rotateZ":rz,
                "scaleX":sx, "scaleY":sy, "scaleZ":sz}
    if objs:
        for obj in objs:
            for attr in attrDict:
                if attrDict[attr]:
                    cmds.setKeyframe("{}.{}".format(obj, attr),
                                      time=(time, time))

def get_timeline_range():
    """ Return the current information about Maya timeline

    This function finds the minimum and maximum frame numbers of the current
    playback range, and calculate the difference to find timeline range.

    Returns:
        min_time (float): first frame on the current Maya playback.
        max_time (float): last frame on the current Maya playback.
        time_range (float): the range of the current Maya playback.

    """  
    min_time = cmds.playbackOptions(query=True, minTime=True)
    max_time = cmds.playbackOptions(query=True, maxTime=True)
    time_range = min_time - max_time + 1

    return min_time, max_time, time_range

def channel_box_selection():
    """ Return the selected channelboxes

    This function returns all the selected channelboxes in the format of
    object.attribute.

    Returns:
        channels_sel (list): a list of all the channelbox selections

    """      
    channels_sel = []
    
    # get selected objects, returns None if nothing is selected
    mObj = cmds.channelBox('mainChannelBox', query=True,
                                             mainObjectList=True)
    sObj = cmds.channelBox('mainChannelBox', query=True,
                                             shapeObjectList=True)
    hObj = cmds.channelBox('mainChannelBox', query=True,
                                             historyObjectList=True)
    oObj = cmds.channelBox('mainChannelBox', query=True,
                                             outputObjectList=True)

    # get selected attributes, returns None if nothing is selected
    mAttr = cmds.channelBox('mainChannelBox', query=True,
                             selectedMainAttributes=True)
    sAttr = cmds.channelBox('mainChannelBox', query=True,
                             selectedShapeAttributes=True)
    hAttr = cmds.channelBox('mainChannelBox', query=True,
                             selectedHistoryAttributes=True)
    oAttr = cmds.channelBox('mainChannelBox', query=True,
                             selectedOutputAttributes=True)

    # pair object and attribute together and check if they exist in Maya
    if mObj and mAttr:
        channels_sel.extend(["%s.%s"%(loop_obj, loop_attr)
                             for loop_obj in mObj for loop_attr in mAttr
                             if cmds.objExists("%s.%s"%(loop_obj, loop_attr))])
    if sObj and sAttr:
        channels_sel.extend(["%s.%s"%(loop_obj, loop_attr)
                             for loop_obj in sObj for loop_attr in sAttr
                             if cmds.objExists("%s.%s"%(loop_obj, loop_attr))])
    if hObj and hAttr:
        channels_sel.extend(["%s.%s"%(loop_obj, loop_attr)
                             for loop_obj in hObj for loop_attr in hAttr
                             if cmds.objExists("%s.%s"%(loop_obj, loop_attr))])
    if oObj and oAttr:
        channels_sel.extend(["%s.%s"%(loop_obj, loop_attr)
                             for loop_obj in oObj for loop_attr in oAttr
                             if cmds.objExists("%s.%s"%(loop_obj, loop_attr))])
     
    return channels_sel

def double_warning(msg, title='warning!'):
    """ Give a Qt warning message and a Maya logging message

    This function takes a string and gives a QMessageBox warning plus a Maya
    logging message from that string.

    Arguments:
        msg (str): message to be displayed in warning and logging.
        title (str): window title of the QMessageBox.

    """  
    cmds.warning(msg)
    QtWidgets.QMessageBox.warning(None, title, msg)

def get_world_matrix(ctl):
    """ Take one control and give back its world position and rotation

    This function takes one transform node and returns its position
    and rotation in world space.

    Arguments:
        ctl (str): a transform node

    Returns:
        pos (list): world position of the ctl, returns None if ctl is invalid
        pos (list): world rotation of the ctl, returns None if ctl is invalid

    """
    # check if ctl exists and is a transform node
    transform = cmds.ls(ctl, type="transform")
    if transform:
        pos = cmds.xform(ctl, query=True, translation=True, worldSpace=True)
        rot = cmds.xform(ctl, query=True, rotation=True, worldSpace=True)
    else:
        pos = None
        rot = None

    return pos, rot

def apply_world_matrix(ctl, pos, rot):
    """ Take a control and apply a given world position and rotation on it

    This function takes one transform node and a set of world position and
    rotation, and applies the latter on the former

    Arguments:
        ctl (str): a transform node
        pos (list): a world position
        rot (list): a world rotation

    """
    # check if ctl exists and is a transform node
    transform = cmds.ls(ctl, type="transform")
    if transform:
        cmds.xform(ctl, translation=pos, worldSpace=True)
        cmds.xform(ctl, rotation=rot, worldSpace=True)

class customIntValidator(QtGui.QIntValidator):
    """ Modify a QIntValidator so it will take an empty string

    This function reimplements the validate method of QIntValidator to
    accommodate an empty string user input.

    Returns:
        QValidator.Acceptable (QValidator): regular QValidator response
        value (str): text that goes into QLineEdit
        pos (list): position of the text

    """
    def validate(self, value, pos):
        value = value.strip().title()
        if value == "":
            return QtGui.QValidator.Acceptable, value, pos

        return super(customIntValidator, self).validate(value, pos)

def get_maya_window():
    """ Get Maya's main window and wrap it as QMainWindow

    This function takes Maya's main window and wraps as QMainWindow so it can
    be set as parent for any Qt objects

    Returns:
        window (QMainWindow): a QMainWindow that wraps around Maya's window

    """
    window = OpenMayaUI.MQtUtil.mainWindow()
    window = shiboken.wrapInstance(long(window), QtWidgets.QMainWindow)
    
    return window

class SpaceSwitchTool(QtWidgets.QDialog):
    """ UI class for space switching

    Arguments:
        parent (QMainWindow|None):
            parent: accepts Maya's main window so this tool can be a children
                    of Maya's interface.

    Attributes:
        _instruction_msg (str): overall instruction.
        _default_source_label (str): instruction of what to load in source.
        _default_target_label (str): instruction of what to load in target.
        _default_ctl_label (str): instruction of what to load in control.
        _spaceSwitch_data_dict (dict): dictionary data of source, target,
                                       and control
        _start_frame (str): start frame number in string, for QLineEdit
        _end_frame (str): end frame number in string, for QLineEdit

    """

    def __init__(self, parent=None):
        '''
        '''
        # set up main UI
        super(SpaceSwitchTool, self).__init__(parent)
        self.setWindowTitle("Space Switch Tool")
        self.setFixedWidth(500)

        self._instruction_msg = "\nPlease follow the instructions below\n"
        self._default_source_label = ("--- select your current space "
                                      "switch attr, and load ---")
        self._default_target_label = ("--- switch to your target space switch "
                                      "value, keep attr selected and load ---")
        self._default_ctl_label = "--- select your target control ---"

        self._spaceSwitch_data_dict = {"source space":[],
                                       "target space":[],
                                       "target control":""}
        self._start_frame = str(int(cmds.playbackOptions(
                                    query=True, minTime=True)))
        self._end_frame = str(int(cmds.playbackOptions(
                                    query=True, maxTime=True)))
        
        # build UI
        self.buildWidgets()
        self.buildLayouts()
        self.connectSignals()

    def buildWidgets(self):
        '''
        '''
        warning_icon = QtWidgets.QApplication.style().standardIcon(
                       QtWidgets.QStyle.SP_MessageBoxWarning)
        warning_pixmap = QtGui.QPixmap(warning_icon.pixmap(32,32))
        self._warning_icon_label = QtWidgets.QLabel()
        self._warning_icon_label.setPixmap(warning_pixmap)
        self._instruction_label = QtWidgets.QLabel(self._instruction_msg)
        # self._instruction_label.setAlignment(QtCore.Qt.AlignCenter)

        self._load_ctl_btn = QtWidgets.QPushButton("Load Control")
        self._load_ctl_btn.setFixedSize(90,30)
        self._load_ctl_label = QtWidgets.QLabel(self._default_ctl_label)
        self._load_ctl_label.setAlignment(QtCore.Qt.AlignCenter)
        
        self._load_source_btn = QtWidgets.QPushButton("Load Source")
        self._load_source_btn.setFixedSize(90,30)
        self._load_source_label = QtWidgets.QLabel(self._default_source_label)
        self._load_source_label.setAlignment(QtCore.Qt.AlignCenter)
        
        self._load_target_btn = QtWidgets.QPushButton("Load Target")
        self._load_target_btn.setFixedSize(90,30)
        self._load_target_label = QtWidgets.QLabel(self._default_target_label)
        self._load_target_label.setAlignment(QtCore.Qt.AlignCenter)
              
        self._currentFrame_radbtn = QtWidgets.QRadioButton("current frame")
        self._currentFrame_radbtn.setChecked(True)
        self._bakeKeyframes_radbtn = QtWidgets.QRadioButton("bake keyframes")
        self._everyFrame_radbtn = QtWidgets.QRadioButton("bake every frame")     

        self._set_time_range_chkbx = QtWidgets.QCheckBox("set time range")
        self._start_frame_field = QtWidgets.QLineEdit(self._start_frame)
        self._start_frame_field.setValidator(customIntValidator())
        self._start_frame_field.setFixedWidth(40)
        self._end_frame_field = QtWidgets.QLineEdit(self._end_frame)
        self._end_frame_field.setValidator(customIntValidator())
        self._end_frame_field.setFixedWidth(40)
        self._connect_label = QtWidgets.QLabel("to")

        self._swtich_btn = QtWidgets.QPushButton("Switch Space")

    def buildLayouts(self):
        '''
        '''
        self._master_lyt = QtWidgets.QVBoxLayout(self)
        self._instruction_lyt = QtWidgets.QHBoxLayout(self)
        self._load_ctl_lyt = QtWidgets.QHBoxLayout(self)
        self._load_source_lyt = QtWidgets.QHBoxLayout(self)
        self._load_target_lyt = QtWidgets.QHBoxLayout(self)
        self._time_range_option_lyt = QtWidgets.QHBoxLayout(self)
        self._time_range_widget = QtWidgets.QWidget()
        self._time_range_widget.setDisabled(True)
        self._time_range_lyt = QtWidgets.QHBoxLayout(self._time_range_widget)
        self._bake_mode_lyt = QtWidgets.QHBoxLayout(self)

        self._master_lyt.addLayout(self._instruction_lyt)
        self._master_lyt.addLayout(self._load_ctl_lyt)
        self._master_lyt.addLayout(self._load_source_lyt)
        self._master_lyt.addLayout(self._load_target_lyt)
        self._master_lyt.addLayout(self._bake_mode_lyt)
        self._master_lyt.addLayout(self._time_range_option_lyt)
        self._master_lyt.addWidget(self._swtich_btn)

        self._instruction_lyt.addStretch()
        self._instruction_lyt.addWidget(self._warning_icon_label)
        self._instruction_lyt.addWidget(self._instruction_label)
        self._instruction_lyt.addStretch()
        self._load_ctl_lyt.addWidget(self._load_ctl_btn)
        self._load_ctl_lyt.addWidget(self._load_ctl_label)
        self._load_source_lyt.addWidget(self._load_source_btn)
        self._load_source_lyt.addWidget(self._load_source_label)
        self._load_target_lyt.addWidget(self._load_target_btn)
        self._load_target_lyt.addWidget(self._load_target_label)
        self._bake_mode_lyt.addWidget(self._currentFrame_radbtn)
        self._bake_mode_lyt.addWidget(self._bakeKeyframes_radbtn)
        self._bake_mode_lyt.addWidget(self._everyFrame_radbtn)
        self._bake_mode_lyt.addStretch()
        self._time_range_option_lyt.addWidget(self._set_time_range_chkbx)
        self._time_range_option_lyt.addWidget(self._time_range_widget)
        self._time_range_lyt.addWidget(self._start_frame_field)
        self._time_range_lyt.addWidget(self._connect_label)
        self._time_range_lyt.addWidget(self._end_frame_field)
        self._time_range_lyt.addStretch()

    def connectSignals(self):
        '''
        '''
        self._load_source_btn.clicked.connect(partial(self.loadAttrValue,
                                                  "source space"))
        self._load_target_btn.clicked.connect(partial(self.loadAttrValue,
                                                  "target space"))
        self._load_ctl_btn.clicked.connect(self.loadTargetControl)
        self._swtich_btn.clicked.connect(self.switchSpace)
        self._set_time_range_chkbx.stateChanged.connect(self._toggleTimeRange)
        self._start_frame_field.editingFinished.connect(self._setStartFrame)
        self._end_frame_field.editingFinished.connect(self._setEndFrame)

    def _toggleTimeRange(self):
        '''
        '''
        state = self._set_time_range_chkbx.isChecked()
        self._time_range_widget.setEnabled(state)

    def _setStartFrame(self):
        '''
        no QSpinbox because we do not want the arrow
        '''
        # get rid of 0 padding
        value_str = self._start_frame_field.text()
        end_value_str = self._end_frame
        if value_str == "":
            self._start_frame_field.setText(self._start_frame)
            return

        self._start_frame = value_str
        if int(value_str) >= int(end_value_str):
            new_value_str = str(int(value_str) + 1)
            self._end_frame_field.blockSignals(True)
            self._end_frame_field.setText(new_value_str)
            self._end_frame_field.blockSignals(False)
            self._end_frame = new_value_str

    def _setEndFrame(self):
        '''
        no QSpinbox because we do not want the arrow
        '''
        value_str = self._end_frame_field.text()
        start_value_str = self._start_frame
        if value_str == "":
            self._end_frame_field.setText(self._end_frame)
            return

        self._end_frame = value_str   
        if int(value_str) <= int(start_value_str):
            new_value_str = str(int(value_str) - 1)
            self._start_frame_field.blockSignals(True)
            self._start_frame_field.setText(new_value_str)
            self._start_frame_field.blockSignals(False)
            self._start_frame = new_value_str

    def loadAttrValue(self, key):
        '''
        '''
        self.setFocus()

        data = []
        sel = cmds.ls(selection=True)
        if len(sel) == 1: # only allow user to select one obj
            attr = channel_box_selection()
            if len(attr) == 1: # only allow user to select one attr
                value = cmds.getAttr(attr[0])
                self._spaceSwitch_data_dict[key] = [attr[0], value]
                if key == "source space":
                    self._load_source_label.setText("{}  {}".format(
                                                             attr[0], value))
                else: # key == "target space"
                    self._load_target_label.setText("{}  {}".format(
                                                             attr[0], value))
                return

        self._spaceSwitch_data_dict[key] = []
        if key == "source space":
            double_warning("invalid selection\n{}".format(
                                            self._default_source_label))
            self._load_source_label.setText(self._default_source_label)
        else:# key == "target space"
            double_warning("invalid selection\n{}".format(
                                            self._default_target_label))
            self._load_target_label.setText(self._default_target_label)


    def loadTargetControl(self):
        '''
        '''
        self.setFocus()

        sel = cmds.ls(selection=True, type="transform")
        if len(sel) == 1:
            self._load_ctl_label.setText(sel[0])
            self._spaceSwitch_data_dict["target control"] = sel[0]
        else:
            double_warning("invalid selection\n{}".format(
                                        self._default_ctl_label))
            self._spaceSwitch_data_dict["target control"] = ""
            self._load_ctl_label.setText(self._default_ctl_label)

    def validateData(self):
        '''
        '''
        for key, value in self._spaceSwitch_data_dict.iteritems():
            if not value:
                return False
            if key == "source space" or key == "target space":
                node, attr = value[0].split(".")
                if not cmds.attributeQuery(attr, node=node, exists=True):
                    return False
            else: # "target control"
                if not cmds.objExists(value):
                    return False

        return True

    def switchSpace(self):
        '''
        existing need to identify with the source
        user must not have other space switch in btw the time range??
        '''
        self.setFocus()
        cmds.undoInfo(openChunk=True)
        lock_viewport()
        try: # huge try block to take care of undo chunk
            if self.validateData():
                current_frame = cmds.currentTime(query=True)
                ctl = self._spaceSwitch_data_dict["target control"]
                source_space = self._spaceSwitch_data_dict["source space"][0]
                source_value = self._spaceSwitch_data_dict["source space"][1]
                target_space = self._spaceSwitch_data_dict["target space"][0]
                target_value = self._spaceSwitch_data_dict["target space"][1]

                if self._currentFrame_radbtn.isChecked():
                    self.setSpaceSwitch(current_frame, ctl,
                                        source_space, source_value,
                                        target_space, target_value,)
                else:
                    range_start = int(self._start_frame_field.text())
                    range_end = int(self._end_frame_field.text())
                    keyframes = cmds.keyframe(ctl, query=True,
                                                   timeChange=True) or []
                    keyframes = list(set(keyframes)) # rid of duplicates
                    keyframes.sort()

                    if self._bakeKeyframes_radbtn.isChecked():
                        ref_keys = keyframes[:] # save if for reference
                        if self._set_time_range_chkbx.isChecked():
                            # only get the keys within set range
                            new_keys = []
                            for k in keyframes:
                                if range_start <= k <= range_end:
                                    new_keys.append(k)
                            keyframes = new_keys

                        if not keyframes:
                            double_warning("no keys to bake!")
                            raise Exception # escape

                        matrixData = []
                        for key in keyframes:
                            cmds.currentTime(key, edit=True)
                            cmds.setAttr(source_space, source_value)
                            cmds.setKeyframe(source_space)
                            pos, rot = get_world_matrix(ctl)
                            matrixData.append((pos, rot))

                        # check if closing swap will run
                        if len(keyframes) > 1 and keyframes[-1] < ref_keys[-1]:
                            cmds.currentTime(keyframes[-1], edit=True)
                            end_pos, end_rot = get_world_matrix(ctl)
                            
                            # this may or may not be key so we have to be sure
                            # go to previos frame of the closing switch and save data
                            cmds.currentTime(keyframes[-1] - 1, edit=True)
                            prev_pos, prev_rot = get_world_matrix(ctl)


                        if keyframes[0] > ref_keys[0]:
                            self.setSpaceSwitch(keyframes[0], ctl,
                                                source_space, source_value,
                                                target_space, target_value,)
                            keyframes = keyframes[1:]
                            matrixData = matrixData[1:]

                        # make sure keyframes is not emptied from the first check
                        if keyframes and keyframes[-1] < ref_keys[-1]:
                            # flip target and source to close chunk
                            # self.setSpaceSwitch(keyframes[-1], ctl,
                            #                     target_space, target_value,
                            #                     source_space, source_value,)
                            
                            # cannot use setSpaceSwitch since matrix already
                            # been changed
                            cmds.currentTime(keyframes[-1], edit=True)
                            cmds.setAttr(source_space, source_value)
                            cmds.setKeyframe(source_space)
                            apply_world_matrix(ctl, end_pos, end_rot)
                            create_transform_keys(objects=[ctl],
                                                tx=True, ty=True, tz=True,
                                                rx=True, ry=True, rz=True)

                            cmds.currentTime(keyframes[-1] - 1, edit=True)
                            cmds.setAttr(target_space, target_value)
                            cmds.setKeyframe(target_space)
                            apply_world_matrix(ctl, prev_pos, prev_rot)
                            create_transform_keys(objects=[ctl],
                                                tx=True, ty=True, tz=True,
                                                rx=True, ry=True, rz=True)

                            # as closing, need to somehow fix previous frame which is messed up by mid or start
                            # need to get the correct matrix
                            keyframes = keyframes[:-1]
                            matrixData = matrixData[:-1]

                        # anything right on top or outside will run regularly
                        # anything on the insde will make a swap
                        # inside or outside refers to the outermost two keys
                        for i, key in enumerate(keyframes):
                            cmds.currentTime(key, edit=True)
                            cmds.setAttr(target_space, target_value)
                            cmds.setKeyframe(target_space)
                            pos, rot = matrixData[i]
                            apply_world_matrix(ctl, pos, rot)
                            create_transform_keys(objects=[ctl],
                                                tx=True, ty=True, tz=True,
                                                rx=True, ry=True, rz=True)

                    # situation, when keyframes is [] or 1 item only or 2
                    # when range is within keyframes, need to set a switch key (either start or end or both)
                    # test with auto key off                    
                    # keyframes
                    # need to set focus on other widget
                    else: # self._everyFrame_radbtn_radbtn.isChecked()
                        if not self._set_time_range_chkbx.isChecked():
                            range_start, range_end, frame_range = (
                                                    get_timeline_range())
                        time_range = range(int(range_start),
                                           int(range_end) + 1)
                        # intersected_frames =[f for f in time_range
                        #                        if f in keyframes]
                        print keyframes
                        print time_range

                        # time_range size will always be 2 oe more, no need to
                        # check
                        matrixData = []
                        for key in time_range:
                            cmds.currentTime(key, edit=True)
                            cmds.setAttr(source_space, source_value)
                            cmds.setKeyframe(source_space)
                            pos, rot = get_world_matrix(ctl)
                            matrixData.append((pos, rot))

                        # print intersected_frames
                        if keyframes[0] < time_range[0]:
                            self.setSpaceSwitch(time_range[0], ctl,
                                                source_space, source_value,
                                                target_space, target_value,)
                            time_range = time_range[1:]
                            matrixData = matrixData[1:]

                        if keyframes[-1] > time_range[-1]:
                            self.setSpaceSwitch(time_range[-1], ctl,
                                                target_space, target_value,
                                                source_space, source_value,)
                            time_range = time_range[:-1]
                            matrixData = matrixData[:-1]

                        for i, key in enumerate(time_range):
                            cmds.currentTime(key, edit=True)
                            cmds.setAttr(target_space, target_value)
                            cmds.setKeyframe(target_space)
                            pos, rot = matrixData[i]
                            apply_world_matrix(ctl, pos, rot)
                            create_transform_keys(objects=[ctl],
                                                tx=True, ty=True, tz=True,
                                                rx=True, ry=True, rz=True)

                    cmds.currentTime(current_frame, edit=True)

        except Exception,e:
            print "There is an Error in try block!!!"
            print str(e)
        finally:
            unlock_viewport()
            cmds.undoInfo(closeChunk=True)

    def setSpaceSwitch(self, frame, ctl, source_space, source_value,
                                         target_space, target_value):
        '''
        set the transition key from one space to another
        '''
        # get current frame's matrix
        cmds.currentTime(frame, edit=True)
        pos, rot = get_world_matrix(ctl)

        # go to previous frame and key
        prev_frame = frame - 1.0
        cmds.currentTime(prev_frame, edit=True)
        cmds.setAttr(source_space, source_value)
        cmds.setKeyframe(source_space)
        create_transform_keys(objects=[ctl], tx=True, ty=True,
                            tz=True, rx=True, ry=True, rz=True)

        # return to current frame and apply original matrix
        cmds.currentTime(frame, edit=True)
        cmds.setAttr(target_space, target_value)
        cmds.setKeyframe(target_space)
        apply_world_matrix(ctl, pos, rot)
        create_transform_keys(objects=[ctl], tx=True, ty=True, tz=True,
                                           rx=True, ry=True, rz=True)

    def mouseReleaseEvent(self, event):
        '''
        '''
        super(SpaceSwitchTool, self).mouseReleaseEvent(event)
        self.setFocus()

    def closeEvent(self, event):
        '''
        '''
        super(SpaceSwitchTool, self).closeEvent(event)


mayaPtr = get_maya_window()
win = SpaceSwitchTool(mayaPtr)
win.show()

'''
import sys
path = "C:\\Users\\Danny Hsu\\Desktop\\animTools\\spaceSwitchTool"

if path not in sys.path:
    sys.path.append(path)
    
import spaceSwitch_tool_v001_DH as sst
reload(sst)
'''
