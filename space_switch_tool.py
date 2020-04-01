"""
MODULE: space_switch_tool

CLASSES:
    SpaceSwitchTool: class for main UI and space switch methods.
    CustomIntValidator: class to reimplement the QIntValidator.
"""
import logging
from functools import partial

import maya.mel as mel
import maya.cmds as cmds
import shiboken2 as shiboken
import maya.api.OpenMaya as om
import maya.OpenMayaUI as OpenMayaUI
from PySide2 import QtWidgets, QtGui, QtCore


LOGGER = logging.getLogger(__name__)


def to_list(nodes):
    """check the input, if gets a single node, put it in a list, pass if gets
    a list, and returns None if not a string or list.

    Args:
        nodes (str|list): one or multiple nodes

    Returns:
        list: a list of nodes.
    """
    # check data type, make sure turn single object into list
    if isinstance(nodes, basestring):
        nodes = [nodes]
    elif isinstance(nodes, list): # need to modify to accept () or {} type?
        pass
    else:
        nodes = None

    return nodes


def check_node_type(nodes, checkTypes=["transform"]):
    """check the node types of a list of nodes, return True if they all
    match the given type, False if not.

    Args:
        nodes (str|list): one or multiple nodes
        checkTypes (str|list): any node type in Maya

    Returns:
        bool: True if successful, False otherwise.
    """
    # check data type, make sure turn single object into list
    nodes = to_list(nodes)
    checkTypes = to_list(checkTypes)
    if nodes is None or checkTypes is None: # if none str or list were given
        return False

    for node in nodes:
        if cmds.nodeType(node) not in checkTypes:
            return False

    return True


def check_rotate_order(source, target):
    """query the rotate orders of source and target and check if they are
    identical, raise warning if not.

    Args:
        source (str): a source transform node.
        target (str): a target transform node.

    Returns:
        bool: True if successful, False otherwise.
    """
    # check if inputs are transform or joint nodes
    # only these two types of nodes have rotate order (?)
    if check_node_type([source, target], ["transform", "joint"]):
        source_rotateOrder = cmds.xform(source, query=True, rotateOrder=True)
        target_rotateOrder = cmds.xform(target, query=True, rotateOrder=True)
        if source_rotateOrder == target_rotateOrder:
            return True

    return False


def constrain_move_key(driver, driven, constraintType):
    """Taken from Veronica ikfk matching script, instead of using xform, which
    is behaving inconsistently, use constraint, get the value and apply.

    TODO: figure out why the broken code works on norman rig but not the legit one ;_;

    Args:
        driver (str): a parent transform node.
        driven (str): a child transform node.
        constraintType (str): any Maya constraint type.

    Returns:
        list: a list of nodes that is not None and exists in Maya.
    """
    # create a hold positio locator at where driver is (avoid cycle error)  
    loc = cmds.spaceLocator(name="temp")[0]
    cmds.parent(loc, driver)
    cmds.setAttr("{}.translate".format(loc), 0, 0, 0)
    cmds.setAttr("{}.rotate".format(loc), 0, 0, 0)
    cmds.parent(loc, world=True)
    # cmds.delete(cmds.parentConstraint(driver, loc, maintainOffset=False))

    execStr = ('con = cmds.%s(loc, driven, maintainOffset=False)[0]'
               % constraintType)
    exec(execStr)
    location = cmds.xform(driven, query=True, translation=True,
                          worldSpace=True)
    rotation = cmds.xform(driven, query=True, rotation=True, worldSpace=True)
    cmds.delete(con, loc)
    return location, rotation

    # # this works in Veronica's script(pyMel), try to replicate it
    # execStr = ('con = %s(driver, driven, maintainOffset=False)'
    #            % constraintType)
    # exec(execStr)
    # location = cmds.xform(driven, query=True, translation=True,
    #                       worldSpace=True)
    # rotation = cmds.xform(driven, query=True, rotation=True, worldSpace=True)
    # delete(con.name())
    # return location, rotation


def lock_viewport():
    """Finds Maya viewport and locks it down to save viewport feedback time.
    """
    for pnl in cmds.lsUI(panels=True):
        ctrl = cmds.panel(pnl, query=True, control=True)
        if ctrl and cmds.getPanel(typeOf=pnl) == 'modelPanel': # viewport
            cmds.control(ctrl, edit=True, manage=False)
         

def unlock_viewport():
    """Finds Maya viewport and unlocks it. It is a clean-up function for
    lock_viewport function.
    """
    for pnl in cmds.lsUI(panels=True):
        ctrl = cmds.panel(pnl, query=True, control=True)
        if ctrl and cmds.getPanel(typeOf=pnl) == 'modelPanel': # viewport
            cmds.control(ctrl, edit=True, manage=True)


def filter_invalid_objects(objects):
    """Takes any list and filters out None and non-existing nodes.

    Args:
        objects (list): a list of any nodes.

    Returns:
        list: a list of nodes that is not None and exists in Maya.
    """
    objs = []
    if not objects: # return if nothing is given
        return objs

    for loop_obj in filter(None, objects):
        if cmds.objExists(loop_obj):
            objs.append(loop_obj)
                
    return objs


def create_transform_keys(objects=None, time=None,
                          tx=False, ty=False, tz=False,
                          rx=False, ry=False, rz=False,
                          sx=False, sy=False, sz=False):
    """Takes an object list and sets keys on the transform channels
    based on the flags given. It is primary used to deal with cmds.setKeyframe
    function so we can avoid repeating string formatting.

    Args:
        objects (list): a list of any transform nodes.
        time (int|float|None): frame number to set key frame on, set on
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
    objs = filter_invalid_objects(objects) or cmds.ls(selection=True)
    if not objs: # return if nothing is found
        LOGGER.warning("No valid objects were found to create transform keys")
        return

    if time is None:
        time = cmds.currentTime(query=True)

    attr_dict = {"translateX":tx, "translateY":ty, "translateZ":tz,
                 "rotateX":rx, "rotateY":ry, "rotateZ":rz,
                 "scaleX":sx, "scaleY":sy, "scaleZ":sz}
    
    for obj in objs:
        for attr in attr_dict:
            if attr_dict[attr] is True:
                cmds.setKeyframe("{}.{}".format(obj, attr),
                                  time=(time, time))


def get_timeline_range():
    """Returns the minimum and maximum frame numbers of the current
    playback range, and calculates the difference to find time range.

    Returns:
        tuple: first frame, last frame and range of the timeline.
    """  
    min_time = cmds.playbackOptions(query=True, minTime=True)
    max_time = cmds.playbackOptions(query=True, maxTime=True)
    time_range = int(min_time - max_time + 1)

    return min_time, max_time, time_range


def channel_box_selection():
    """Returns the selected channelboxes in the format of
    object.attribute.

    Returns:
        list: a list of all the channelbox selections.
    """      
    channels_sel = []
    
    # get selected objects, returns None if nothing is selected
    m_obj = cmds.channelBox(
        'mainChannelBox', query=True, mainObjectList=True
    )
    s_obj = cmds.channelBox(
        'mainChannelBox', query=True, shapeObjectList=True
    )
    h_obj = cmds.channelBox(
        'mainChannelBox', query=True, historyObjectList=True
    )
    o_obj = cmds.channelBox(
        'mainChannelBox', query=True, outputObjectList=True
    )

    # get selected attributes, returns None if nothing is selected
    m_attr = cmds.channelBox('mainChannelBox', query=True,
                             selectedMainAttributes=True)
    s_attr = cmds.channelBox('mainChannelBox', query=True,
                             selectedShapeAttributes=True)
    h_attr = cmds.channelBox('mainChannelBox', query=True,
                             selectedHistoryAttributes=True)
    o_attr = cmds.channelBox('mainChannelBox', query=True,
                             selectedOutputAttributes=True)

    # pair object and attribute together and check if they exist in Maya
    if m_obj and m_attr:
        channels_sel.extend(
            "{}.{}".format(loop_obj, loop_attr)
            for loop_obj in m_obj for loop_attr in m_attr
            if cmds.objExists("{}.{}".format(loop_obj, loop_attr))
        )
    if s_obj and s_attr:
        channels_sel.extend(
            "{}.{}".format(loop_obj, loop_attr)
            for loop_obj in s_obj for loop_attr in s_attr
            if cmds.objExists("{}.{}".format(loop_obj, loop_attr))
        )
    if h_obj and h_attr:
        channels_sel.extend(
            "{}.{}".format(loop_obj, loop_attr)
            for loop_obj in h_obj for loop_attr in h_attr
            if cmds.objExists("{}.{}".format(loop_obj, loop_attr))
        )
    if o_obj and o_attr:
        channels_sel.extend(
            "{}.{}".format(loop_obj, loop_attr)
            for loop_obj in o_obj for loop_attr in o_attr
            if cmds.objExists("{}.{}".format(loop_obj, loop_attr))
        )
     
    return channels_sel


def double_warning(msg, title='warning!'):
    """Takes a string and gives a QMessageBox warning plus a logging message
    from that string.

    Args:
        msg (str): message to be displayed in warning and logging.
        title (str): window title of the QMessageBox.
    """  
    LOGGER.warning(msg)
    QtWidgets.QMessageBox.warning(None, title, msg)


def get_world_matrix(ctl):
    """Takes one transform node and returns its position and rotation
    in world space.

    Args:
        ctl (str): a transform node.

    Returns:
        tuple: world position and rotation of the control,
               and returns None if control is invalid.
    """
    # check if ctl exists and is a transform node
    transform = cmds.ls(ctl, type="transform")
    if transform: # TODO: log this
        pos = cmds.xform(ctl, query=True, translation=True, worldSpace=True)
        rot = cmds.xform(ctl, query=True, rotation=True, worldSpace=True)
    else:
        LOGGER.warning("This is not a transfomr node!")
        pos = None
        rot = None

    return pos, rot


def apply_world_matrix(ctl, pos, rot):
    """Takes one transform node and a set of world position and
    rotation, and applies the latter on the former.

    Args:
        ctl (str): a transform node.
        pos (list): a world position.
        rot (list): a world rotation.
    """
    # check if ctl exists and is a transform node
    transform = cmds.ls(ctl, type="transform")
    if transform:
        cmds.xform(ctl, translation=pos, worldSpace=True)
        cmds.xform(ctl, rotation=rot, worldSpace=True)


def get_maya_window():
    """Takes Maya's main window and wraps it as QMainWindow so it can
    be set as parent of any Qt objects.

    Returns:
        QMainWindow: a QMainWindow that wraps around Maya's window.
    """
    window = OpenMayaUI.MQtUtil.mainWindow()
    window = shiboken.wrapInstance(long(window), QtWidgets.QMainWindow)
    
    return window


class CustomIntValidator(QtGui.QIntValidator):
    """Reimplements the validate method of QIntValidator to
    accommodate an empty string user input.
    """
    def validate(self, value, pos):
        """Catches an empty string and returns with acceptable value and pos.

        Returns:
            tuple: QValidator, text value and text position
        """
        value = value.strip().title()
        if value == "":
            return QtGui.QValidator.Acceptable, value, pos

        return super(CustomIntValidator, self).validate(value, pos)


class SpaceSwitchTool(QtWidgets.QDialog):
    """UI class for space switching.

    TODO: take care of QLineEdit setFocus() issue.
    """
    def __init__(self, parent=None):
        """Sets up all UI components.

        Args:
            parent (QMainWindow|None): accepts parent's window.
        """
        # set main QDialog parameters
        super(SpaceSwitchTool, self).__init__(parent)
        self.setWindowTitle("Space Switch Tool")
        self.setFixedWidth(550)

        # set label messages
        self._instruction_msg = "\nPlease follow the instructions below:\n"
        self._default_source_lbl = ("--- select your current space "
                                    "switch attr, and load ---")
        self._default_target_lbl = ("--- switch to your target space switch "
                                    "value, keep attr selected and load ---")
        self._default_ctl_lbl = "--- select your target control ---"
        self._default_empty_lbl = "--- empty ---"

        # declare and initialize variable
        self._space_switch_data_dict = {"target control":"",
                                        "source space":[],
                                        "target space":[]}
        self._ikfk_switch_data_dict = {"shoulder joint":"",
                                       "elbow joint":"",
                                       "wrist joint":"",
                                       "fk shoulder":"",
                                       "fk elbow":"",
                                       "fk wrist":"",
                                       "fk switch":[],
                                       "fk visibility":[], # assume 0 and 1
                                       "ik elbow":"",
                                       "ik wrist":"",
                                       "ik switch":[],
                                       "ik visibility":[]} # assume 0 and 1
        self._start_frame = str(int(cmds.playbackOptions(
                                query=True, minTime=True)))
        self._end_frame = str(int(cmds.playbackOptions(
                              query=True, maxTime=True)))
        
        # build tab widgets
        self._tabs = QtWidgets.QTabWidget()
        self._space_switch_tab = QtWidgets.QWidget()
        self._ik_fk_switch_tab = QtWidgets.QWidget()

        # build instruction widgets
        self._warning_icon_lbl = QtWidgets.QLabel()
        self._instruction_lbl = QtWidgets.QLabel(self._instruction_msg)

        # build space switch widgets
        self._load_ctl_btn = QtWidgets.QPushButton("Load Control")
        self._load_ctl_lbl = QtWidgets.QLabel(self._default_ctl_lbl)
        self._load_source_btn = QtWidgets.QPushButton("Load Source")
        self._load_source_lbl = QtWidgets.QLabel(self._default_source_lbl)
        self._load_target_btn = QtWidgets.QPushButton("Load Target")
        self._load_target_lbl = QtWidgets.QLabel(self._default_target_lbl)
        
        # build ik/fk switch widgets
        self._load_shoulder_jnt_btn = QtWidgets.QPushButton("Load Shoulder "
                                                            "Joint")
        self._load_shoulder_jnt_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_elbow_jnt_btn = QtWidgets.QPushButton("Load Elbow Joint")
        self._load_elbow_jnt_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_wrist_jnt_btn = QtWidgets.QPushButton("Load Wrist Joint")
        self._load_wrist_jnt_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_fk_shoulder_btn = QtWidgets.QPushButton("Load FK Shoulder")
        self._load_fk_shoulder_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_fk_elbow_btn = QtWidgets.QPushButton("Load FK Elbow")
        self._load_fk_elbow_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_fk_wrist_btn = QtWidgets.QPushButton("Load FK Wrist")
        self._load_fk_wrist_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_fk_switch_btn = QtWidgets.QPushButton("Load FK Switch")
        self._load_fk_switch_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_fk_vis_btn = QtWidgets.QPushButton("Load FK Visibility")
        self._load_fk_vis_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_ik_elbow_btn = QtWidgets.QPushButton("Load IK Elbow")
        self._load_ik_elbow_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_ik_wrist_btn = QtWidgets.QPushButton("Load IK Wrist")
        self._load_ik_wrist_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_ik_switch_btn = QtWidgets.QPushButton("Load IK Switch")
        self._load_ik_switch_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_ik_vis_btn = QtWidgets.QPushButton("Load IK Visibility")
        self._load_ik_vis_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._ikfk_mode_btnGrp = QtWidgets.QButtonGroup(self)
        self._ik_to_fk_radbtn = QtWidgets.QRadioButton("IK -> FK")
        self._fk_to_ik_radbtn = QtWidgets.QRadioButton("FK -> IK")

        # build extra option widgets
        self._timeline_btnGrp = QtWidgets.QButtonGroup(self)
        self._currentFrame_radbtn = QtWidgets.QRadioButton("current frame")
        self._bakeKeyframes_radbtn = QtWidgets.QRadioButton("bake keyframes")
        self._everyFrame_radbtn = QtWidgets.QRadioButton("bake every frame")     
        self._set_time_range_chkbx = QtWidgets.QCheckBox("set time range")
        self._start_frame_field = QtWidgets.QLineEdit(self._start_frame)
        self._end_frame_field = QtWidgets.QLineEdit(self._end_frame)
        self._connect_lbl = QtWidgets.QLabel("to")
        self._time_range_widget = QtWidgets.QWidget() # allow enable / disable

        # build execution widget
        self._swtich_btn = QtWidgets.QPushButton("Switch Space")

        # set up UI
        self._set_widgets()
        self._set_layouts()
        self._connect_signals()

    def _set_widgets(self):
        '''Sets all parameters for the widgets.
        '''
        # set up tabs
        self._tabs.addTab(self._space_switch_tab, "space switch") # index 0
        self._tabs.addTab(self._ik_fk_switch_tab, "ik/fk switch") # index 1

        # set instruction
        warning_icon = QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.SP_MessageBoxWarning
        )
        warning_pixmap = QtGui.QPixmap(warning_icon.pixmap(32,32))
        self._warning_icon_lbl.setPixmap(warning_pixmap)

        # set space switch loading buttons
        self._load_ctl_btn.setFixedSize(90,30)
        self._load_ctl_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._load_source_btn.setFixedSize(90,30)
        self._load_source_lbl.setAlignment(QtCore.Qt.AlignCenter)     
        self._load_target_btn.setFixedSize(90,30)
        self._load_target_lbl.setAlignment(QtCore.Qt.AlignCenter)

        # set ik/fk switch loading buttons
        self._load_shoulder_jnt_btn.setFixedSize(120,30)
        self._load_shoulder_jnt_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._load_elbow_jnt_btn.setFixedSize(120,30)
        self._load_elbow_jnt_lbl.setAlignment(QtCore.Qt.AlignCenter)     
        self._load_wrist_jnt_btn.setFixedSize(120,30)
        self._load_wrist_jnt_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._load_fk_shoulder_btn.setFixedSize(120,30)
        self._load_fk_shoulder_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._load_fk_elbow_btn.setFixedSize(120,30)
        self._load_fk_elbow_lbl.setAlignment(QtCore.Qt.AlignCenter)     
        self._load_fk_wrist_btn.setFixedSize(120,30)
        self._load_fk_wrist_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._load_fk_switch_btn.setFixedSize(120,30)
        self._load_fk_switch_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._load_fk_vis_btn.setFixedSize(120,30)
        self._load_fk_vis_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._load_ik_elbow_btn.setFixedSize(120,30)
        self._load_ik_elbow_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._load_ik_wrist_btn.setFixedSize(120,30)
        self._load_ik_wrist_lbl.setAlignment(QtCore.Qt.AlignCenter)     
        self._load_ik_switch_btn.setFixedSize(120,30)
        self._load_ik_switch_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._load_ik_vis_btn.setFixedSize(120,30)
        self._load_ik_vis_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._ik_to_fk_radbtn.setChecked(True)
        self._ikfk_mode_btnGrp.addButton(self._ik_to_fk_radbtn)
        self._ikfk_mode_btnGrp.addButton(self._fk_to_ik_radbtn)
        
        # set extra options
        self._timeline_btnGrp.addButton(self._currentFrame_radbtn)
        self._timeline_btnGrp.addButton(self._bakeKeyframes_radbtn)
        self._timeline_btnGrp.addButton(self._everyFrame_radbtn)
        self._currentFrame_radbtn.setChecked(True)
        self._start_frame_field.setValidator(CustomIntValidator())
        self._start_frame_field.setFixedWidth(40)
        self._end_frame_field.setValidator(CustomIntValidator())
        self._end_frame_field.setFixedWidth(40)
        self._time_range_widget.setDisabled(True)

    def _set_layouts(self):
        """Sets all layout components.
        """
        # initialize layouts
        master_lyt = QtWidgets.QVBoxLayout(self)
        instruction_lyt = QtWidgets.QHBoxLayout(self)
        space_switch_lyt = QtWidgets.QVBoxLayout(self._space_switch_tab)
        ik_fk_switch_lyt = QtWidgets.QVBoxLayout(self._ik_fk_switch_tab)
        ik_fk_switch_sub_lyt = QtWidgets.QHBoxLayout(self._ik_fk_switch_tab)
        ik_fk_switch_sub1_lyt = QtWidgets.QVBoxLayout(self._ik_fk_switch_tab)
        ik_fk_switch_sub2_lyt = QtWidgets.QVBoxLayout(self._ik_fk_switch_tab)

        # initialize fk layouts
        load_ctl_lyt = QtWidgets.QHBoxLayout(self)
        load_source_lyt = QtWidgets.QHBoxLayout(self)
        load_target_lyt = QtWidgets.QHBoxLayout(self)

        # initialize ik layouts
        load_shoulder_jnt_lyt = QtWidgets.QHBoxLayout(self)
        load_elbow_jnt_lyt = QtWidgets.QHBoxLayout(self)
        load_wrist_jnt_lyt = QtWidgets.QHBoxLayout(self)
        load_fk_shoulder_lyt = QtWidgets.QHBoxLayout(self)
        load_fk_elbow_lyt = QtWidgets.QHBoxLayout(self)
        load_fk_wrist_lyt = QtWidgets.QHBoxLayout(self)
        load_fk_switch_lyt = QtWidgets.QHBoxLayout(self)
        load_fk_vis_lyt = QtWidgets.QHBoxLayout(self)
        load_ik_elbow_lyt = QtWidgets.QHBoxLayout(self)
        load_ik_wrist_lyt = QtWidgets.QHBoxLayout(self)
        load_ik_switch_lyt = QtWidgets.QHBoxLayout(self)
        load_ik_vis_lyt = QtWidgets.QHBoxLayout(self)
        ikfk_mode_lyt = QtWidgets.QHBoxLayout(self)

        # initialize extra option layouts
        time_range_option_lyt = QtWidgets.QHBoxLayout(self)
        time_range_lyt = QtWidgets.QHBoxLayout(self._time_range_widget)
        bake_mode_lyt = QtWidgets.QHBoxLayout(self)

        # organize master layout
        master_lyt.addLayout(instruction_lyt)
        master_lyt.addWidget(self._tabs)
        master_lyt.addLayout(bake_mode_lyt)
        master_lyt.addLayout(time_range_option_lyt)
        master_lyt.addWidget(self._swtich_btn)

        # organize tab layouts
        space_switch_lyt.addLayout(load_ctl_lyt)
        space_switch_lyt.addLayout(load_source_lyt)
        space_switch_lyt.addLayout(load_target_lyt)
        space_switch_lyt.addStretch()
        ik_fk_switch_lyt.addLayout(ik_fk_switch_sub_lyt)
        ik_fk_switch_lyt.addLayout(ikfk_mode_lyt)
        ik_fk_switch_sub_lyt.addLayout(ik_fk_switch_sub1_lyt)
        ik_fk_switch_sub_lyt.addLayout(ik_fk_switch_sub2_lyt)
        ik_fk_switch_sub1_lyt.addLayout(load_shoulder_jnt_lyt)
        ik_fk_switch_sub1_lyt.addLayout(load_elbow_jnt_lyt)
        ik_fk_switch_sub1_lyt.addLayout(load_wrist_jnt_lyt)
        ik_fk_switch_sub1_lyt.addLayout(load_ik_switch_lyt)
        ik_fk_switch_sub1_lyt.addLayout(load_ik_vis_lyt)
        ik_fk_switch_sub1_lyt.addLayout(load_ik_elbow_lyt)
        ik_fk_switch_sub1_lyt.addStretch()
        ik_fk_switch_sub2_lyt.addLayout(load_fk_shoulder_lyt)
        ik_fk_switch_sub2_lyt.addLayout(load_fk_elbow_lyt)
        ik_fk_switch_sub2_lyt.addLayout(load_fk_wrist_lyt)
        ik_fk_switch_sub2_lyt.addLayout(load_fk_switch_lyt)
        ik_fk_switch_sub2_lyt.addLayout(load_fk_vis_lyt)
        ik_fk_switch_sub2_lyt.addLayout(load_ik_wrist_lyt)
        ik_fk_switch_sub2_lyt.addLayout(ikfk_mode_lyt)
        ik_fk_switch_sub2_lyt.addStretch()

        # organize instruction layouts
        instruction_lyt.addStretch()
        instruction_lyt.addWidget(self._warning_icon_lbl)
        instruction_lyt.addWidget(self._instruction_lbl)
        instruction_lyt.addStretch()

        # organize space switch tab layouts
        load_ctl_lyt.addWidget(self._load_ctl_btn)
        load_ctl_lyt.addWidget(self._load_ctl_lbl)
        load_source_lyt.addWidget(self._load_source_btn)
        load_source_lyt.addWidget(self._load_source_lbl)
        load_target_lyt.addWidget(self._load_target_btn)
        load_target_lyt.addWidget(self._load_target_lbl)

        # organize ik/fk switch tab layouts
        load_shoulder_jnt_lyt.addWidget(self._load_shoulder_jnt_btn)
        load_shoulder_jnt_lyt.addWidget(self._load_shoulder_jnt_lbl)
        load_elbow_jnt_lyt.addWidget(self._load_elbow_jnt_btn)
        load_elbow_jnt_lyt.addWidget(self._load_elbow_jnt_lbl)
        load_wrist_jnt_lyt.addWidget(self._load_wrist_jnt_btn)
        load_wrist_jnt_lyt.addWidget(self._load_wrist_jnt_lbl)
        load_fk_shoulder_lyt.addWidget(self._load_fk_shoulder_btn)
        load_fk_shoulder_lyt.addWidget(self._load_fk_shoulder_lbl)
        load_fk_elbow_lyt.addWidget(self._load_fk_elbow_btn)
        load_fk_elbow_lyt.addWidget(self._load_fk_elbow_lbl)
        load_fk_wrist_lyt.addWidget(self._load_fk_wrist_btn)
        load_fk_wrist_lyt.addWidget(self._load_fk_wrist_lbl)
        load_fk_switch_lyt.addWidget(self._load_fk_switch_btn)
        load_fk_switch_lyt.addWidget(self._load_fk_switch_lbl)
        load_fk_vis_lyt.addWidget(self._load_fk_vis_btn)
        load_fk_vis_lyt.addWidget(self._load_fk_vis_lbl)
        load_ik_elbow_lyt.addWidget(self._load_ik_elbow_btn)
        load_ik_elbow_lyt.addWidget(self._load_ik_elbow_lbl)
        load_ik_wrist_lyt.addWidget(self._load_ik_wrist_btn)
        load_ik_wrist_lyt.addWidget(self._load_ik_wrist_lbl)
        load_ik_switch_lyt.addWidget(self._load_ik_switch_btn)
        load_ik_switch_lyt.addWidget(self._load_ik_switch_lbl)
        load_ik_vis_lyt.addWidget(self._load_ik_vis_btn)
        load_ik_vis_lyt.addWidget(self._load_ik_vis_lbl)
        ikfk_mode_lyt.addStretch()
        ikfk_mode_lyt.addWidget(self._ik_to_fk_radbtn)
        ikfk_mode_lyt.addWidget(self._fk_to_ik_radbtn)

        # organize extra option layouts
        bake_mode_lyt.addWidget(self._currentFrame_radbtn)
        bake_mode_lyt.addWidget(self._bakeKeyframes_radbtn)
        bake_mode_lyt.addWidget(self._everyFrame_radbtn)
        bake_mode_lyt.addStretch()
        time_range_option_lyt.addWidget(self._set_time_range_chkbx)
        time_range_option_lyt.addWidget(self._time_range_widget)
        time_range_lyt.addWidget(self._start_frame_field)
        time_range_lyt.addWidget(self._connect_lbl)
        time_range_lyt.addWidget(self._end_frame_field)
        time_range_lyt.addStretch()

    def _connect_signals(self):
        """Connects each widget to their method.
        """
        # connect space switch buttons
        self._load_source_btn.clicked.connect(partial(self.load_attr_value,
                                                      "source space",
                                                      self._load_source_lbl))
        self._load_target_btn.clicked.connect(partial(self.load_attr_value,
                                                      "target space",
                                                      self._load_target_lbl))
        self._load_ctl_btn.clicked.connect(partial(self.load_target_control, 
                                                   "target control",
                                                   self._load_ctl_lbl))

        # connect ik/fk switch buttons
        self._load_shoulder_jnt_btn.clicked.connect(
            partial(self.load_target_control,
                    "shoulder joint",
                    self._load_shoulder_jnt_lbl,
                    "joint")
        )
        self._load_elbow_jnt_btn.clicked.connect(
            partial(self.load_target_control,
                    "elbow joint",
                    self._load_elbow_jnt_lbl,
                    "joint")
        )
        self._load_wrist_jnt_btn.clicked.connect(
            partial(self.load_target_control, 
                    "wrist joint",
                    self._load_wrist_jnt_lbl,
                    "joint")
        )
        self._load_fk_shoulder_btn.clicked.connect(
            partial(self.load_target_control,
                    "fk shoulder",
                    self._load_fk_shoulder_lbl)
        )
        self._load_fk_elbow_btn.clicked.connect(
            partial(self.load_target_control,
                    "fk elbow",
                    self._load_fk_elbow_lbl)
        )
        self._load_fk_wrist_btn.clicked.connect(
            partial(self.load_target_control, 
                    "fk wrist",
                    self._load_fk_wrist_lbl)
        )
        self._load_fk_switch_btn.clicked.connect(
            partial(self.load_attr_value,
                    "fk switch",
                    self._load_fk_switch_lbl)
        )
        self._load_fk_vis_btn.clicked.connect(
            partial(self.load_attr_value,
                    "fk visibility",
                    self._load_fk_vis_lbl)
        )
        self._load_ik_elbow_btn.clicked.connect(
            partial(self.load_target_control,
                    "ik elbow",
                    self._load_ik_elbow_lbl)
        )
        self._load_ik_wrist_btn.clicked.connect(
            partial(self.load_target_control, 
                    "ik wrist",
                    self._load_ik_wrist_lbl)
        )
        self._load_ik_switch_btn.clicked.connect(
            partial(self.load_attr_value,
                    "ik switch",
                    self._load_ik_switch_lbl)
        )
        self._load_ik_vis_btn.clicked.connect(
            partial(self.load_attr_value,
                    "ik visibility",
                    self._load_ik_vis_lbl)
        )
        
        # connect extra option
        self._set_time_range_chkbx.stateChanged.connect(
            self._toggle_time_range
        )
        self._start_frame_field.editingFinished.connect(self._set_start_frame)
        self._end_frame_field.editingFinished.connect(self._set_end_frame)

        # connect execution
        self._swtich_btn.clicked.connect(self.execute_switch)

    def _toggle_time_range(self):
        """When checked, makes custom time range section available for user.
        """
        state = self._set_time_range_chkbx.isChecked()
        self._time_range_widget.setEnabled(state)

    def _set_start_frame(self):
        """When edited, checks if the frame number entered is valid. Modifies
        the value if frame number is invalid.
        """
        value_str = self._start_frame_field.text()
        end_value_str = self._end_frame
        if not value_str:
            self._start_frame_field.setText(self._start_frame)
            return

        self._start_frame = value_str
        if int(value_str) >= int(end_value_str):
            new_value_str = str(int(value_str) + 1)
            self._end_frame_field.blockSignals(True)
            self._end_frame_field.setText(new_value_str)
            self._end_frame_field.blockSignals(False)
            self._end_frame = new_value_str

    def _set_end_frame(self):
        """When edited, checks if the frame number entered is valid. Modifies
        the value if frame number is invalid.
        """
        value_str = self._end_frame_field.text()
        start_value_str = self._start_frame
        if not value_str:
            self._end_frame_field.setText(self._end_frame)
            return

        self._end_frame = value_str   
        if int(value_str) <= int(start_value_str):
            new_value_str = str(int(value_str) - 1)
            self._start_frame_field.blockSignals(True)
            self._start_frame_field.setText(new_value_str)
            self._start_frame_field.blockSignals(False)
            self._start_frame = new_value_str

    def load_attr_value(self, key, lbl):
        """Takes a key value and stores the attribute selected by the user into
        internal data using that key, also edits the label.

        Args:
            key (str): decides which attribute key to edit in
                       self._space_switch_data_dict.
            btn (QLabel): decides which label to change 
        """
        sel = cmds.ls(selection=True)
        attr = channel_box_selection()

        # only allow user to select one object and one attribute
        if len(sel) is 1 and len(attr) is 1:
            value = cmds.getAttr(attr[0])
            if key in ["source space", "target space"]:
                self._space_switch_data_dict[key] = [attr[0], value]
            else:
                self._ikfk_switch_data_dict[key] = [attr[0], value]
            lbl.setText("{}  {}".format(attr[0], value))
            return # escape from here if selected attribute is valid

        # if selection is invalid, restore to default instruction
        if key == "source space":
            self._space_switch_data_dict[key] = []
            double_warning(
                "invalid selection!\n{}".format(self._default_source_lbl)
            )
            lbl.setText(self._default_source_lbl)

        elif key == "target space":
            self._space_switch_data_dict[key] = []
            double_warning(
                "invalid selection!\n{}".format(self._default_target_lbl)
            )
            lbl.setText(self._default_target_lbl)

        else: # attributes for ik/fk switch
            self._ikfk_switch_data_dict[key] = []
            double_warning(
                "invalid selection!\n--- please load {} ---".format(key)
            )
            lbl.setText(self._default_empty_lbl)

    def load_target_control(self, key, lbl, typ="transform"):
        """Takes a key value and stores the control selected by the user into
        internal data using that key, also edits the label.

        Args:
            key (str): decides which control key to edit in
                       self._space_switch_data_dict.
            btn (QLabel): decides which label to change
            typ (str): limits the selected object type
        """
        sel = cmds.ls(selection=True, type=typ)
        if len(sel) == 1: # only allow one selected object
            if key == "target control":
                self._space_switch_data_dict[key] = sel[0]
            else:
                self._ikfk_switch_data_dict[key] = sel[0]
            lbl.setText(sel[0])
            return # escape from here if selected transform is valid

        # if selection is invalid, restore to default instruction
        if key == "target control": # if none or more than one control selected
            self._space_switch_data_dict[key] = ""
            double_warning(
                "invalid selection!\n{}".format(self._default_ctl_lbl)
            )
            lbl.setText(self._default_ctl_lbl)
        else: # controls for ik/fk switch
            self._ikfk_switch_data_dict[key] = ""
            double_warning(
                "invalid selection!\n--- please select {} ---".format(key)
            )
            lbl.setText(self._default_empty_lbl)

    def validate_space_switch_data(self):
        """Validates all required data right before executing the
        space_switch method.

        Returns:
            bool: True if successful, False otherwise.
        """
        for key, value in self._space_switch_data_dict.iteritems():
            if not value: # check if user input is empty
                return False
            if key == "source space" or key == "target space":
                node, attr = value[0].split(".")
                # check if the attributes still exist in the scene
                if not cmds.attributeQuery(attr, node=node, exists=True):
                    return False
            else: # key == "target control"
                # check if the control still exist in the scene
                if not cmds.objExists(value):
                    return False

        # all user inputs are still valid
        return True

    def validate_ikfk_switch_data(self):
        """Validates all required data right before executing the
        ikfk_switch method.

        Returns:
            bool: True if successful, False otherwise.
        """
        for key, value in self._ikfk_switch_data_dict.iteritems():
            if not value: # check if user input is empty
                return False
            if key in ["fk switch", "ik switch",
                       "fk visibility", "ik visibility"]:
                node, attr = value[0].split(".")
                # check if the attributes still exist in the scene
                if not cmds.attributeQuery(attr, node=node, exists=True):
                    return False
            else: # key == control or joint
                # check if the object still exist in the scene
                if not cmds.objExists(value):
                    return False

        # all user inputs are still valid
        return True

    def execute_switch(self):
        """Run the switch operation based on the tab loaded, either
        space switch or ik/fk switch.
        """
        if self._tabs.currentWidget() is self._space_switch_tab:
            self.space_switch()
        else: # self._tabs.currentWidget() is self._ik_fk_switch_tab
            self.ikfk_switch()

    def space_switch(self):
        """Executes the main space switch operation using internal data.

        TODO: check what happen if user have other space switch in between
              the set time range.

        TODO: too long at the moment, figure out a way to break this method up.

        TODO: need to check rotate order, otherwise bad!
        """
        # check internal data to make sure user did not remove or rename stuffs
        # from the scene randomly
        if not self.validate_space_switch_data():
            double_warning(
                "Attributes and control are invalid!"
                "\nPlease follow instruction!"
            )
            return

        cmds.undoInfo(openChunk=True)
        lock_viewport()
        # huge try block is used here to take care of undo chunk
        # TODO: replace it using decorator
        try: 
            current_frame = cmds.currentTime(query=True)
            ctl = self._space_switch_data_dict["target control"]
            source_space = self._space_switch_data_dict["source space"][0]
            source_value = self._space_switch_data_dict["source space"][1]
            target_space = self._space_switch_data_dict["target space"][0]
            target_value = self._space_switch_data_dict["target space"][1]

            if self._currentFrame_radbtn.isChecked():
                self.set_space_switch(current_frame, ctl,
                                    source_space, source_value,
                                    target_space, target_value,)
            else:
                range_start = int(self._start_frame_field.text())
                range_end = int(self._end_frame_field.text())
                keyframes = cmds.keyframe(ctl, query=True, timeChange=True)
                if keyframes is None:
                    keyframes = [] # set to empty list instead
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
                        raise Exception # escape the block

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
                        # go to previous frame of the closing switch
                        # and save data
                        cmds.currentTime(keyframes[-1] - 1, edit=True)
                        prev_pos, prev_rot = get_world_matrix(ctl)


                    if keyframes[0] > ref_keys[0]:
                        self.set_space_switch(keyframes[0], ctl,
                                              source_space, source_value,
                                              target_space, target_value,)
                        
                        # remove first keyframe from data
                        keyframes = keyframes[1:]
                        matrixData = matrixData[1:]

                    # make sure keyframes is not emptied from the first check
                    if keyframes and keyframes[-1] < ref_keys[-1]:
                        # flip target and source to close chunk
                        # cannot use set_space_switch method since
                        # current matrix has already been changed
                        cmds.currentTime(keyframes[-1], edit=True)
                        cmds.setAttr(source_space, source_value)
                        cmds.setKeyframe(source_space)
                        apply_world_matrix(ctl, end_pos, end_rot)
                        create_transform_keys(objects=[ctl],
                                              tx=True, ty=True, tz=True,
                                              rx=True, ry=True, rz=True)

                        # set key for the frame before
                        cmds.currentTime(keyframes[-1] - 1, edit=True)
                        cmds.setAttr(target_space, target_value)
                        cmds.setKeyframe(target_space)
                        apply_world_matrix(ctl, prev_pos, prev_rot)
                        create_transform_keys(objects=[ctl],
                                              tx=True, ty=True, tz=True,
                                              rx=True, ry=True, rz=True)

                        # remove last keyframe from data
                        keyframes = keyframes[:-1]
                        matrixData = matrixData[:-1]

                    # anything right on top or outside will run regularly
                    # anything on the insde will make a set_space_switch
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

                # section for 'bake every frame'
                # TODO: check situations when keyframes is [] or 1-2 items
                else: # self._everyFrame_radbtn_radbtn.isChecked()
                    if not self._set_time_range_chkbx.isChecked():
                        range_start, range_end, frame_range = (
                            get_timeline_range()
                        )
                    time_range = range(int(range_start),
                                       int(range_end) + 1)

                    # time_range size will always be 2 or more,
                    # so skip checking
                    matrixData = []
                    for key in time_range:
                        cmds.currentTime(key, edit=True)
                        cmds.setAttr(source_space, source_value)
                        cmds.setKeyframe(source_space)
                        pos, rot = get_world_matrix(ctl)
                        matrixData.append((pos, rot))

                    if keyframes[0] < time_range[0]:
                        self.set_space_switch(time_range[0], ctl,
                                              source_space, source_value,
                                              target_space, target_value,)
                        time_range = time_range[1:]
                        matrixData = matrixData[1:]

                    if keyframes[-1] > time_range[-1]:
                        self.set_space_switch(time_range[-1], ctl,
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

                # return to current frame
                cmds.currentTime(current_frame, edit=True)

        except Exception, e:
            double_warning(
                "There is an Error in try block!\n{}".format(str(e))
            )

        finally: # clean up
            unlock_viewport()
            cmds.undoInfo(closeChunk=True)

    def set_space_switch(self, frame, ctl, source_space, source_value,
                         target_space, target_value):
        """Used when the keyframe needs to make a transition from source space
        to target space.

        Args:
            frame (int|float): frame number where the switch will be made.
            ctl (str): control used for space switch operation.
            source_space (str): an attribute represents space to switch from.
            source_value (type): value in source space attribute,
                                 type depends on the rig used.
            target_space (str): an attribute represents space to switch to.
            target_value (type): value in target space attribute,
                                 type depends on the rig used.
        """
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

    def ikfk_switch(self):
        """Executes the main ik/fk switch operation using internal data.

        TODO: check what happen if user have other space switch in between
              the set time range.

        TODO: too long at the moment, figure out a way to break this method up.

        TODO: for some rigs (max), the wrist flips when doing FK --> IK, and
              for some weird reason, apply matrix twice fixes it (close enough).
              best to find out what happen here

        TODO: some rigs have separate visibility control (like FS rigs), some incorporate
              in the ikfk switch (like Caroline, and max I guess, which has both options),
              so far we make it work for Caronline, but need to think of a solution for this.
        """
        # check internal data to make sure user did not remove or rename stuffs
        # from the scene randomly

        # # test using Norman
        # self._ikfk_switch_data_dict["shoulder joint"] = "max:Shoulder_L"
        # self._ikfk_switch_data_dict["elbow joint"] = "max:Elbow_L"
        # self._ikfk_switch_data_dict["wrist joint"] = "max:Wrist_L"
        # self._ikfk_switch_data_dict["ik wrist"] = "max:IKArm_L"
        # self._ikfk_switch_data_dict["ik elbow"] = "max:PoleArm_L"
        # self._ikfk_switch_data_dict["fk visibility"] = ["max:FKIKArm_L.FKVis", 0]
        # self._ikfk_switch_data_dict["ik visibility"] = ["max:FKIKArm_L.IKVis", 1]
        # self._ikfk_switch_data_dict["ik switch"] = ["max:FKIKArm_L.FKIKBlend", 10]
        # self._ikfk_switch_data_dict["fk switch"] = ["max:FKIKArm_L.FKIKBlend", 0]
        # self._ikfk_switch_data_dict["fk shoulder"] = "max:FKShoulder_L"
        # self._ikfk_switch_data_dict["fk elbow"] = "max:FKElbow_L"
        # self._ikfk_switch_data_dict["fk wrist"] = "max:FKWrist_L"
        
        # # test using Caroline     
        # self._ikfk_switch_data_dict["shoulder joint"] = "CarolineRig_v4_REF:rig_left_shoulder"
        # self._ikfk_switch_data_dict["elbow joint"] = "CarolineRig_v4_REF:rig_left_elbow"
        # self._ikfk_switch_data_dict["wrist joint"] = "CarolineRig_v4_REF:rig_left_wrist"
        # self._ikfk_switch_data_dict["ik wrist"] = "CarolineRig_v4_REF:ctl_ik_left_hand"
        # self._ikfk_switch_data_dict["ik elbow"] = "CarolineRig_v4_REF:ctl_ik_left_elbow"
        # self._ikfk_switch_data_dict["fk visibility"] = ["CarolineRig_v4_REF:ctl_left_arm_settings.IKFK", 1]
        # self._ikfk_switch_data_dict["ik visibility"] = ["CarolineRig_v4_REF:ctl_left_arm_settings.IKFK", 0]
        # self._ikfk_switch_data_dict["ik switch"] = ["CarolineRig_v4_REF:ctl_left_arm_settings.IKFK", 0]
        # self._ikfk_switch_data_dict["fk switch"] = ["CarolineRig_v4_REF:ctl_left_arm_settings.IKFK", 1]
        # self._ikfk_switch_data_dict["fk shoulder"] = "CarolineRig_v4_REF:ctl_fk_left_shoulder"
        # self._ikfk_switch_data_dict["fk elbow"] = "CarolineRig_v4_REF:ctl_fk_left_elbow"
        # self._ikfk_switch_data_dict["fk wrist"] = "CarolineRig_v4_REF:ctl_fk_left_wrist"
             
        if not self.validate_ikfk_switch_data():
            double_warning(
                "Either joints, controls or attributes loaded are invalid!"
                "\nPlease read the tooltip of each button for instruction."
            )
            return

        current_frame = cmds.currentTime(query=True)
        prev_frame = current_frame - 1.0
        shoulder_jnt = self._ikfk_switch_data_dict["shoulder joint"]
        elbow_jnt = self._ikfk_switch_data_dict["elbow joint"]
        wrist_jnt = self._ikfk_switch_data_dict["wrist joint"]
        fk_shoulder = self._ikfk_switch_data_dict["fk shoulder"]
        fk_elbow = self._ikfk_switch_data_dict["fk elbow"]
        fk_wrist = self._ikfk_switch_data_dict["fk wrist"]
        fk_switch_attr = self._ikfk_switch_data_dict["fk switch"][0]
        fk_switch_value = self._ikfk_switch_data_dict["fk switch"][1]
        fk_vis_attr = self._ikfk_switch_data_dict["fk visibility"][0]
        fk_vis_value = self._ikfk_switch_data_dict["fk visibility"][1]
        ik_elbow = self._ikfk_switch_data_dict["ik elbow"]
        ik_wrist = self._ikfk_switch_data_dict["ik wrist"]
        ik_switch_attr = self._ikfk_switch_data_dict["ik switch"][0]
        ik_switch_value = self._ikfk_switch_data_dict["ik switch"][1]
        ik_vis_attr = self._ikfk_switch_data_dict["ik visibility"][0]
        ik_vis_value = self._ikfk_switch_data_dict["ik visibility"][1]

        # TODO: maybe integrate this with more clarity
        # check rotate order, give it a warning if something is wrong
        rotate_order_flag = False
        msg = ("The following joints and FK controls do not "
               "share the same rotate order:\n\n")
        for jnt, ctl in [[shoulder_jnt, fk_shoulder], [elbow_jnt, fk_elbow],
                         [wrist_jnt, fk_wrist]]:
            if check_rotate_order(jnt, ctl) is False:
                msg += "{}, {}\n".format(jnt, ctl)
                rotate_order_flag = True

        if rotate_order_flag:
            msg += "\nThe switch result may be incorrect, continue?"
            buttons = (QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            result = QtWidgets.QMessageBox.warning(None,
                                                   'Inconsistency Warning!',
                                                   msg, buttons)
            if result == QtWidgets.QMessageBox.No:
                return

        # HOW TO FIX IT!
        # zero out control first, return both ik and fk to the same position
        # change rotate order on fk controls (same as joints)
        # reposition the control (ik)
        # run tool

        # get joint position and rotation in world space
        shoulder_pos, should_rot = get_world_matrix(shoulder_jnt)
        elbow_pos, elbow_rot = get_world_matrix(elbow_jnt)
        wrist_pos, wrist_rot = get_world_matrix(wrist_jnt)

        # get joint position and rotation
        # shoulder_pos, should_rot = get_world_matrix(shoulder_jnt, ws_rot=False)
        # elbow_pos, elbow_rot = get_world_matrix(elbow_jnt, ws_rot=False)
        # wrist_pos, wrist_rot = get_world_matrix(wrist_jnt, ws_rot=False)

        if self._ik_to_fk_radbtn.isChecked():
            
            # should_rot = cmds.xform(shoulder_jnt, query=True, rotation=True)
            # elbow_rot = cmds.xform(elbow_jnt, query=True, rotation=True)
            # wrist_rot = cmds.xform(wrist_jnt, query=True, rotation=True)

            # should_rot = cmds.getAttr("{}.rotate".format(shoulder_jnt))[0]
            # elbow_rot = cmds.getAttr("{}.rotate".format(elbow_jnt))[0]
            # wrist_rot = cmds.getAttr("{}.rotate".format(wrist_jnt))[0]

            # go to previous frame            
            cmds.currentTime(prev_frame, edit=True)
            for fk in [fk_shoulder, fk_elbow, fk_wrist]:
                # hold down previous position     
                create_transform_keys(objects=[fk], rx=True, ry=True, rz=True)
            cmds.setKeyframe(fk_switch_attr)
            cmds.setKeyframe(fk_vis_attr)
            cmds.setKeyframe(ik_vis_attr)

            # return to current frame
            cmds.currentTime(current_frame, edit=True)
            cmds.setAttr(fk_switch_attr, fk_switch_value)
            cmds.setKeyframe(fk_switch_attr)
            # cmds.setAttr(fk_vis_attr, int(fk_vis_value))
            # cmds.setKeyframe(fk_vis_attr)
            # cmds.setAttr(ik_vis_attr, int(ik_vis_value)) # does not work for some set up like Caroline
            # cmds.setKeyframe(ik_vis_attr)

            # why does this work but not mine
                       
            # cmds.xform(fk_shoulder, rotation=should_rot)     
            # cmds.xform(fk_elbow, rotation=elbow_rot)    
            # cmds.xform(fk_wrist, rotation=wrist_rot)
            # cmds.setAttr("{}.rotate".format(fk_shoulder), *should_rot)
            # cmds.setAttr("{}.rotateY".format(fk_elbow), elbow_rot[1])
            # cmds.setAttr("{}.rotate".format(fk_wrist), *wrist_rot)
            # create_transform_keys(objects=[fk_shoulder, fk_elbow, fk_wrist],
            #                       rx=True, ry=True, rz=True)

            for fk, value in [[fk_shoulder, should_rot], [fk_elbow, elbow_rot],
                              [fk_wrist, wrist_rot]]:
                cmds.xform(fk, rotation=value, worldSpace=True) # apply in world space
                # cmds.xform(fk, rotation=value) # apply in local space
                # print value
                # cmds.setAttr("{}.rotate".format(fk), *value)
                create_transform_keys(objects=[fk], rx=True, ry=True, rz=True)

        else: # self._fk_to_ik_radbtn.isChecked()
            # vector math
            shoulder_jnt_vector = om.MVector(shoulder_pos)
            elbow_jnt_vector = om.MVector(elbow_pos)
            wrist_jnt_vector = om.MVector(wrist_pos)
            midpoint_vector = ((wrist_jnt_vector - shoulder_jnt_vector) * 0.5
                               + shoulder_jnt_vector)
            aim_vector = ((elbow_jnt_vector - midpoint_vector) * 4
                          + midpoint_vector)
            new_elbow_pos = (aim_vector.x, aim_vector.y, aim_vector.z)
            
            # loc1 = cmds.spaceLocator()[0]
            # cmds.setAttr("{}.t".format(loc1), *elbow_pos)
            # loc2 = cmds.spaceLocator()[0]
            # cmds.setAttr("{}.t".format(loc2), midpoint_vector.x, midpoint_vector.y, midpoint_vector.z)
            # loc3 = cmds.spaceLocator()[0]
            # cmds.setAttr("{}.t".format(loc3), *new_elbow_pos)
            # return

            # new way of getting wrist matrix
            # for some weird reason the wrist flip, but doing twice get it closer ;_;
            wrist_pos, wrist_rot = constrain_move_key(wrist_jnt, ik_wrist, 'parentConstraint')
            
            # go to previous frame            
            cmds.currentTime(prev_frame, edit=True)
            create_transform_keys(objects=[ik_wrist],
                                  tx=True, ty=True, tz=True,
                                  rx=True, ry=True, rz=True)   
            create_transform_keys(objects=[ik_elbow],
                                  tx=True, ty=True, tz=True)
            cmds.setKeyframe(ik_switch_attr)
            cmds.setKeyframe(ik_vis_attr)
            cmds.setKeyframe(fk_vis_attr)

            # return to current frame
            cmds.currentTime(current_frame, edit=True)
            cmds.setAttr(ik_switch_attr, ik_switch_value)
            cmds.setKeyframe(ik_switch_attr)
            # cmds.setAttr(ik_vis_attr, int(ik_vis_value))
            # cmds.setKeyframe(ik_vis_attr)
            # cmds.setAttr(fk_vis_attr, int(fk_vis_value)) # does not work for some set up like Caroline
            # cmds.setKeyframe(fk_vis_attr)
            
            # the orientation of this one is broken (flip 180), could it be rotate order? ask Vineet!
            apply_world_matrix(ik_wrist, wrist_pos, wrist_rot) # apply in world space         
            # cmds.xform(ik_wrist, rotation=wrist_rot) # apply in local space, not working
            # for some weird reason for norman (max), we need to do the wrist twice (flip it back)
            # this may not happen to all the rig (worked on Caroline)
            # get joint position and rotation in world space, again
            wrist_pos, wrist_rot = constrain_move_key(wrist_jnt, ik_wrist, 'parentConstraint')
            apply_world_matrix(ik_wrist, wrist_pos, wrist_rot) # apply in world space
            create_transform_keys(objects=[ik_wrist],
                                  tx=True, ty=True, tz=True,
                                  rx=True, ry=True, rz=True)
            # TODO: need to figure out what happened here :(

            # process elbow
            cmds.xform(ik_elbow, translation=new_elbow_pos, worldSpace=True)
            create_transform_keys(objects=[ik_elbow],
                                  tx=True, ty=True, tz=True)

    def mouseReleaseEvent(self, event):
        """Makes sure when user clicks on the UI it will set UI in focus.
        """
        super(SpaceSwitchTool, self).mouseReleaseEvent(event)
        self.setFocus()


if __name__ == "__main__":
    mayaPtr = get_maya_window()
    win = SpaceSwitchTool(mayaPtr)
    win.show()
