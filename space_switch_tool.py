"""
MODULE: space_switch_tool

CLASSES:
    SpaceSwitchTool: class for main UI and space switch methods.
    CustomIntValidator: class to reimplement the QIntValidator.
"""
import os
import json
import ntpath
import logging
from functools import partial

import maya.mel as mel
import maya.cmds as cmds
import shiboken2 as shiboken
import maya.api.OpenMaya as om
import maya.OpenMayaUI as OpenMayaUI
from PySide2 import QtWidgets, QtGui, QtCore


LOGGER = logging.getLogger(__name__)


def path_leaf(path):
    """Takes a full path name and returns a single file name. Cannot use
    os.path.basename since it does not work with Unix based os.

    Args:
        path (str): full file path.

    Returns:
        str: file name.
    """
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)


def to_list(nodes):
    """Checks the input, if gets a single node, put it in a list, pass if gets
    a list, and returns None if not a string or list.

    Args:
        nodes (str|list): one or multiple nodes.

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


def get_current_folder(subFolder=""):
    """Gets the current file's folder with option of creating a subfolder,
    if current file is not saved, return empty string.

    TODO: test this on Unix to see if "/" causes problem.

    Args:
        subFolder (str): name of the subfolder to create.

    Returns:
        str: directory path of the current folder or subfolder.    
    """
    currentDir = cmds.file(query=True, sceneName=True)
    if currentDir:
        if subFolder:
            subFolder = "/{}".format(subFolder) # add separator
        backupDir = currentDir.replace("/{}".format(cmds.file(query=True,
                                       sceneName=True, shortName=True)),
                                       subFolder)
        if not os.path.isdir(backupDir):
            os.mkdir(backupDir)
        return backupDir
    return ""


def check_node_type(nodes, checkTypes=["transform"]):
    """Checks the node types of a list of nodes, return True if they all
    match the given type, False if not.

    Args:
        nodes (str|list): one or multiple nodes.
        checkTypes (str|list): any node type in Maya.

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
    """Queries the rotate orders of source and target and check if they are
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
    """Taken from Veronica's ikfk matching script, instead of using xform, which
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


def double_warning(msg, title='Warning!'):
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


def open_UI():
    """function call to instantiate a SpaceSwitchTool object.
    """
    global space_switch_win

    try:
        space_switch_win.close()
        # we have to do this silly thing because QDialog messes with
        # static variable somehow. would have worked for QWidget
        SpaceSwitchTool.folder_path_str = space_switch_win.folder_path_str
    except Exception, e:
        LOGGER.warning(e)

    mayaPtr = get_maya_window()
    space_switch_win = SpaceSwitchTool("Space Switch Tool", mayaPtr)
    space_switch_win.show()
    

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
    folder_path_str = ""
    def __init__(self, win_name, parent=None):
        """Sets up all UI components.

        Args:
            parent (QMainWindow|None): accepts parent's window.
        """
        # set main QDialog parameters
        super(SpaceSwitchTool, self).__init__(parent)
        # self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(win_name)
        self.setFixedWidth(350)

        # set label messages
        self._title_txt = "\nPlease follow the instructions below:\n"
        self._tutorial_txt = "\nPlease follow the\ninstructions below:\n"
        self._default_empty_lbl = "--- empty ---"
        if not SpaceSwitchTool.folder_path_str:
            SpaceSwitchTool.folder_path_str = get_current_folder()

        # declare and initialize variable
        self._selected_item = None
        self._file_list_items = {}
        self._space_switch_data_dict = {"mode":"space switch",
                                        "target control":"",
                                        "source space":[],
                                        "target space":[]}
        self._ikfk_switch_data_dict = {"mode":"ikfk switch",
                                       "shoulder joint":"",
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
        self._main_switch_tab = QtWidgets.QWidget()
        self._space_switch_tab = QtWidgets.QWidget()
        self._ik_fk_switch_tab = QtWidgets.QWidget()

        # build instruction widgets
        self._warning_icon_lbl = QtWidgets.QLabel()
        self._instruction_lbl = QtWidgets.QLabel(self._title_txt)
        self._load_data_btn = QtWidgets.QPushButton()
        self._save_data_btn = QtWidgets.QPushButton()

        # build main switch widgets
        # self._folder_path_lbl = QtWidgets.QLabel("Directory:")
        self._folder_path_field = QtWidgets.QLineEdit(
            SpaceSwitchTool.folder_path_str
        )
        self._load_path_btn = QtWidgets.QPushButton()
        self._refresh_list_btn = QtWidgets.QPushButton()
        self._file_list_widget = QtWidgets.QListWidget() # single selection
        self._list_item_popup_menu = QtWidgets.QMenu(self)
        self._delete_action = QtWidgets.QAction("delete", self)
        self._tutorial_lbl = QtWidgets.QLabel(self._tutorial_txt)

        # build space switch widgets
        self._load_ctl_btn = QtWidgets.QPushButton("Load Control")
        self._load_ctl_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_source_btn = QtWidgets.QPushButton("Load Source")
        self._load_source_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        self._load_target_btn = QtWidgets.QPushButton("Load Target")
        self._load_target_lbl = QtWidgets.QLabel(self._default_empty_lbl)
        
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
        self.populate_list_widget()

    def _set_widgets(self):
        '''Sets all parameters for the widgets.
        '''
        # set up tabs
        self._tabs.addTab(self._main_switch_tab, "main switch") # index 0
        self._tabs.addTab(self._space_switch_tab, "space switch") # index 1
        self._tabs.addTab(self._ik_fk_switch_tab, "ik/fk switch") # index 2

        # set instruction
        warning_icon = QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.SP_MessageBoxWarning
        )
        warning_pixmap = QtGui.QPixmap(warning_icon.pixmap(32,32))
        self._warning_icon_lbl.setPixmap(warning_pixmap)

        load_data_icon = QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.SP_DialogOpenButton
        )
        self._load_data_btn.setIcon(load_data_icon)   

        save_data_icon = QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.SP_DialogSaveButton
        )
        self._save_data_btn.setIcon(save_data_icon)
     
        # main switch widgets
        load_path_icon = QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.SP_DirIcon
        )
        self._load_path_btn.setIcon(load_path_icon)
        self._load_path_btn.setFixedSize(24,24)
        refresh_list_icon = QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.SP_BrowserReload
        )
        self._refresh_list_btn.setIcon(refresh_list_icon)
        self._refresh_list_btn.setFixedSize(24,24)       
        self._file_list_widget.setContextMenuPolicy(
            QtCore.Qt.CustomContextMenu
        )
        self._list_item_popup_menu.addAction(self._delete_action)

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
        title_lyt = QtWidgets.QHBoxLayout(self)
        main_switch_lyt = QtWidgets.QVBoxLayout(self._main_switch_tab)
        main_switch_folder_lyt = QtWidgets.QHBoxLayout(self._main_switch_tab)
        main_switch_list_lyt = QtWidgets.QHBoxLayout(self._main_switch_tab)
        space_switch_lyt = QtWidgets.QVBoxLayout(self._space_switch_tab)
        ik_fk_switch_lyt = QtWidgets.QVBoxLayout(self._ik_fk_switch_tab)
        # ik_fk_switch_sub_lyt = QtWidgets.QHBoxLayout(self._ik_fk_switch_tab)
        # ik_fk_switch_sub1_lyt = QtWidgets.QVBoxLayout(self._ik_fk_switch_tab)
        # ik_fk_switch_sub2_lyt = QtWidgets.QVBoxLayout(self._ik_fk_switch_tab)

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
        master_lyt.addLayout(title_lyt)
        master_lyt.addWidget(self._tabs)
        master_lyt.addLayout(bake_mode_lyt)
        master_lyt.addLayout(time_range_option_lyt)
        master_lyt.addWidget(self._swtich_btn)

        # organize tab layouts
        main_switch_lyt.addLayout(main_switch_folder_lyt)
        main_switch_lyt.addLayout(main_switch_list_lyt)
        space_switch_lyt.addLayout(load_ctl_lyt)
        space_switch_lyt.addLayout(load_source_lyt)
        space_switch_lyt.addLayout(load_target_lyt)
        space_switch_lyt.addStretch()
        # ik_fk_switch_lyt.addLayout(ik_fk_switch_sub_lyt)
        # ik_fk_switch_sub_lyt.addLayout(ik_fk_switch_sub1_lyt)
        # ik_fk_switch_sub_lyt.addLayout(ik_fk_switch_sub2_lyt)
        ik_fk_switch_lyt.addLayout(load_shoulder_jnt_lyt)
        ik_fk_switch_lyt.addLayout(load_elbow_jnt_lyt)
        ik_fk_switch_lyt.addLayout(load_wrist_jnt_lyt)
        ik_fk_switch_lyt.addLayout(load_ik_switch_lyt)
        ik_fk_switch_lyt.addLayout(load_ik_vis_lyt)
        ik_fk_switch_lyt.addLayout(load_ik_elbow_lyt)
        ik_fk_switch_lyt.addLayout(load_ik_wrist_lyt)
        # ik_fk_switch_sub1_lyt.addStretch()
        ik_fk_switch_lyt.addLayout(load_fk_shoulder_lyt)
        ik_fk_switch_lyt.addLayout(load_fk_elbow_lyt)
        ik_fk_switch_lyt.addLayout(load_fk_wrist_lyt)
        ik_fk_switch_lyt.addLayout(load_fk_switch_lyt)
        ik_fk_switch_lyt.addLayout(load_fk_vis_lyt)
        ik_fk_switch_lyt.addLayout(ikfk_mode_lyt)
        # ik_fk_switch_sub2_lyt.addStretch()
        ik_fk_switch_lyt.addLayout(ikfk_mode_lyt)

        # organize instruction layouts
        title_lyt.addStretch()
        title_lyt.addWidget(self._warning_icon_lbl)
        title_lyt.addWidget(self._instruction_lbl)
        title_lyt.addStretch()
        title_lyt.addWidget(self._load_data_btn)
        title_lyt.addWidget(self._save_data_btn)

        # organize main switch tab layouts
        main_switch_folder_lyt.addWidget(self._folder_path_field)
        main_switch_folder_lyt.addWidget(self._load_path_btn)
        main_switch_folder_lyt.addWidget(self._refresh_list_btn)
        main_switch_list_lyt.addWidget(self._file_list_widget)
        main_switch_list_lyt.addWidget(self._tutorial_lbl)

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
        # load title buttons
        self._load_data_btn.clicked.connect(self._load_switch_data)
        self._save_data_btn.clicked.connect(self._save_switch_data)

        # connect main switch buttons
        self._folder_path_field.editingFinished.connect(self._folder_path_changed)
        self._load_path_btn.clicked.connect(self.get_folder_path)
        self._refresh_list_btn.clicked.connect(self.populate_list_widget)
        self._file_list_widget.itemClicked.connect(self._list_item_selected)
        self._file_list_widget.customContextMenuRequested.connect(
            self._context_menu
        )
        self._delete_action.triggered.connect(self._delete_item)

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

    def _context_menu(self, point):
        """Bring out right click menu for listWidget item, and update internal
        data of item selected.

        Args:
            point (QPoint): show coordinates at where mouse is clicked.
        """
        item = self._file_list_widget.selectedItems()
        if item:
            item = item[0] # list widget is limited to single selection
            if item is not self._selected_item:
                self._update_selected_item(item)
            self._list_item_popup_menu.popup(
                self._file_list_widget.mapToGlobal(point)
            )

    def _folder_path_changed(self):
        """When directory is edited, validate the new folder path, and load all
        the switch data indside if folder is valid.

        TODO: when Return is pressed, editingFinished is triggered twice,
              from both Return AND escaping focus. Super annoying!
        """
        folder_name = self._folder_path_field.text()
        if os.path.isdir(folder_name):
            SpaceSwitchTool.folder_path_str = folder_name
        else:
            # in case the directory is no longer valid
            if self.validate_directory():
                self._folder_path_field.setText(
                    SpaceSwitchTool.folder_path_str
                )

        self.setFocus()

    def _update_selected_item(self, item):
        """Updates the self._selected_item with the given item widget and
        populate the corresponding UI components. This method handles item cliked
        (left and right) and also auto selection after deleting a list item.

        Args:
            name (QListWidgetItem): given list widget item object.
        """
        name = item.text()
        data = self._file_list_items[name]
        if data["mode"] == "space switch":
            self._space_switch_data_dict = data.copy()
            self._populate_space_switch_UI()
        else: # data["mode"] == "ikfk switch"
            self._ikfk_switch_data_dict = data.copy()
            self._populate_ikfk_switch_UI()
        self._selected_item = item

    def _list_item_selected(self):
        """Detects when a list item is selected and updates the internal data
        and UI, or deselect when a selected item was clicked (responds only to
        left mouse clikc).
        """
        item = self._file_list_widget.currentItem()
        if item is self._selected_item:
            self._file_list_widget.setItemSelected(item, False) # deselect
            self._selected_item = None
            # leave the data_dict be, no need to empty it when deselect
        else:
            self._update_selected_item(item)

    def _add_item(self, name, data):
        """Internal method that adds the imported data into list widget. This
        method is not responsible for checking whether the data is valid!

        Args:
            name (str): file name, title of the list widget item.
            data (dict): either an space switch or ikfk switch dictionary
        """      
        if self._file_list_widget.findItems(name, QtCore.Qt.MatchExactly):
            double_warning("Item already exists in the list!")
            return

        self._file_list_items[name] = data
        self._file_list_widget.addItem(name)

    def _delete_item(self):
        """Internal method that executes when delete action on the right click
        menu is triggered. Cleans up the internal data.

        NOTE: QListWidget auto-select the next item after item deletion.
        """
        row = self._file_list_widget.currentRow()
        name = self._selected_item.text()
        self._file_list_widget.takeItem(row) # does not clean up
        self._file_list_items.pop(name)
        del self._selected_item # clean up item widget
        
        # handles the next selection, keep consistency in behavior
        item = self._file_list_widget.selectedItems()
        if item:
            item = item[0] # list widget is limited to single selection
            self._update_selected_item(item)
        else: # the list is emptied
            self._selected_item = None

    def _save_switch_data(self):
        """Save space switch JSON file.
        """
        # check currentTab type (currentIndex, currentWidget)
        tab = self._tabs.currentWidget()
        if tab is self._space_switch_tab:
            if self.validate_switch_data("space switch"):
                name = "space switch"
                data = self._space_switch_data_dict
            else:
                double_warning("Data incomplete, please review all entries!")
                return

        elif tab is self._ik_fk_switch_tab:
            if self.validate_switch_data("ikfk switch"):
                name = "ikfk switch"
                data = self._ikfk_switch_data_dict
            else:
                double_warning("Data incomplete, please review all entries!")
                return

        else: # tab is self._main_switch_tab
            # pick the current selected list item and save
            if self._selected_item:
                name = self._selected_item.text()
                data = self._file_list_items[name]
            else:
                double_warning("Please select an item form the list!")
                return

        # if default_dir is empty, goes to the default Maya folder
        default_dir = SpaceSwitchTool.folder_path_str or get_current_folder() 
        default_path = os.path.join(default_dir, "{}.json".format(name))
        file_name = QtWidgets.QFileDialog.getSaveFileName(self, "Save",
                                                          default_path,
                                                          "*.json")[0]
        if file_name:
            with open(file_name, "w") as out_file:
                json.dump(data, out_file)

    def _load_switch_data(self, file_name=None, give_warning=True):
        """Load space switch JSON file.
        """
        if not file_name:
            # if default_dir is empty, goes to the last opened folder
            default_dir = (SpaceSwitchTool.folder_path_str
                           or get_current_folder())
            file_name = QtWidgets.QFileDialog.getOpenFileName(self, "Load",
                                                              default_dir,
                                                              "*.json")[0]
            if not file_name:
                return

        with open(file_name) as in_file:
            try:
                data = json.load(in_file)
            except ValueError, msg: # when JSON file is empty
                double_warning(str(msg))
                return

        tab = self._tabs.currentWidget()
        warning_msg = ("Invalid json file selected!\nMake sure the "
                       "selected json file is a proper\nspace switch "
                       "data and target rigs are loaded in the scene")

        if tab is self._space_switch_tab:
            if self.validate_switch_data("space switch", data):
                self._space_switch_data_dict = data
                self._populate_space_switch_UI()
            else:
                double_warning(warning_msg)

        elif tab is self._ik_fk_switch_tab:
            if self.validate_switch_data("ikfk switch", data):
                self._ikfk_switch_data_dict = data
                self._populate_ikfk_switch_UI()
            else:
                double_warning(warning_msg)

        else: # tab is self._main_switch_tab
            # validate data to see if it belongs to either switch mode
            name = os.path.splitext(path_leaf(file_name))[0]
            valid = (self.validate_switch_data("space switch", data)
                     or self.validate_switch_data("ikfk switch", data))
            if valid:
                self._add_item(name, data)
            else:
                if give_warning: # disable warning when populating list widget
                    double_warning(warning_msg)

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

    def get_folder_path(self):
        """For user to get folder path of a character, and load all the switch
        file into list widget.
        """
        # if default_dir is empty, goes to the last opened folder
        default_dir = SpaceSwitchTool.folder_path_str or get_current_folder()       
        folder_name = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Load a directory", default_dir
        )
        if folder_name:
            # this will NOT trigger the editingFinished for QLineEdit
            self._folder_path_field.setText(folder_name)
            SpaceSwitchTool.folder_path_str = folder_name

        self.setFocus()

    def populate_list_widget(self):
        """Read folder directory and re-populate the list widget.
        """
        # clear list
        self._file_list_widget.clear()
        self._file_list_items = {}

        if self.validate_directory():
            path = SpaceSwitchTool.folder_path_str
            data_files = [f for f in os.listdir(path) if f.endswith(".json")]
            for f in data_files:
                file_path = os.path.join(path, f)
                self._load_switch_data(file_name=file_path, give_warning=False)

    def _populate_space_switch_UI(self):
        """Read internal data and populate the space switch UI.
        """
        # assign variables
        ctl = self._space_switch_data_dict["target control"]
        source_space = self._space_switch_data_dict["source space"][0]
        source_value = self._space_switch_data_dict["source space"][1]
        target_space = self._space_switch_data_dict["target space"][0]
        target_value = self._space_switch_data_dict["target space"][1]

        # populate labels
        self._load_ctl_lbl.setText(ctl)
        self._load_source_lbl.setText("{}  {}".format(source_space,
                                                      source_value))
        self._load_target_lbl.setText("{}  {}".format(target_space,
                                                      target_value))

    def _populate_ikfk_switch_UI(self):
        """Read internal data and populate the ikfk switch UI.
        """
        # assign variables
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

        # populate labels
        self._load_shoulder_jnt_lbl.setText(shoulder_jnt)
        self._load_elbow_jnt_lbl.setText(elbow_jnt)
        self._load_wrist_jnt_lbl.setText(wrist_jnt)
        self._load_fk_shoulder_lbl.setText(fk_shoulder)
        self._load_fk_elbow_lbl.setText(fk_elbow)
        self._load_fk_wrist_lbl.setText(fk_wrist)
        self._load_fk_switch_lbl.setText("{}  {}".format(fk_switch_attr,
                                                         fk_switch_value))
        self._load_fk_vis_lbl.setText("{}  {}".format(fk_vis_attr,
                                                      fk_vis_value))
        self._load_ik_elbow_lbl.setText(ik_elbow)
        self._load_ik_wrist_lbl.setText(ik_wrist)
        self._load_ik_switch_lbl.setText("{}  {}".format(ik_switch_attr,
                                                         ik_switch_value))
        self._load_ik_vis_lbl.setText("{}  {}".format(ik_vis_attr,
                                                      ik_vis_value))

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
        if key in ["source space", "target space"]:
            self._space_switch_data_dict[key] = []
        else: # attributes for ik/fk switch
            self._ikfk_switch_data_dict[key] = []
        double_warning(
            "Invalid selection!\n--- please load {} ---".format(key)
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
        else: # controls for ik/fk switch
            self._ikfk_switch_data_dict[key] = ""
        double_warning(
            "Invalid selection!\n--- please select {} ---".format(key)
        )
        lbl.setText(self._default_empty_lbl)

    def validate_directory(self):
        """Validates directory currently loaded, handles situation where
        directory is modified or deleted by user.

        Returns:
            bool: True if directory still valid, False otherwise.
        """
        if SpaceSwitchTool.folder_path_str:
            if os.path.isdir(SpaceSwitchTool.folder_path_str):
                return True # directory still exists
            else:
                double_warning("Directory {} no longer exists!".format(
                    SpaceSwitchTool.folder_path_str
                ))
                SpaceSwitchTool.folder_path_str = ""

        self._folder_path_field.setText("")
        return False

    def validate_switch_data(self, switch_mode="space switch", data=None):
        """Validates all required data right before executing the
        space_switch / ikfk_switch method.

        TODO: need to have a more thorough check to see if all keys & values
              are correct (right now it does not do that)

        Args:
            data (dict): option for checking imported dictionary data

        Returns:
            bool: True if successful, False otherwise.
        """
        # check for input arg
        if switch_mode == "space switch":
            switch_data = data or self._space_switch_data_dict
            std_keys = ["mode", "target control", "source space",
                        "target space"]
            attr_keys = ["source space", "target space"]
        else: # switch_mode == "ikfk switch"
            switch_data = data or self._ikfk_switch_data_dict
            std_keys = ["mode", "shoulder joint", "elbow joint", "wrist joint",
                        "fk shoulder", "fk elbow", "fk wrist", "fk switch",
                        "fk visibility", "ik elbow", "ik wrist", "ik switch",
                        "ik visibility"]
            attr_keys = ["fk switch", "ik switch", "fk visibility",
                         "ik visibility"]

        # check if the keys are correct!
        if (not set(switch_data.keys()) == set(std_keys)):
            return

        for key, value in switch_data.iteritems():
            if not value: # check if any user input is empty
                return False

            if key in attr_keys:
                if isinstance(value, list) and len(value) == 2:
                    node, attr = value[0].split(".")
                    if not cmds.objExists(node): # check if object still exists
                        return False
                    # check if attribute still exists
                    if not cmds.attributeQuery(attr, node=node, exists=True):
                        return False
                else:
                    return False
            else:
                if isinstance(value, basestring):
                    if key == "mode":
                        if value not in ["space switch", "ikfk switch"]:
                            return False

                    else: # key is a control
                        # check if the control still exist in the scene
                        if not cmds.objExists(value):
                            return False
                else:
                    return False

        # all user inputs are still valid
        return True

    def _check_fk_rotate_order(self, shoulder_jnt, elbow_jnt, wrist_jnt,
                               fk_shoulder, fk_elbow, fk_wrist):
        """Check the consistency between fk controls and joints, give it a
        warning if a mismatch is found.

        TODO: maybe integrate this with more clarity
    
        Args:
            shoulder_jnt (str): shoulder joint from internal data.
            elbow_jnt (str): elbow joint from internal data.
            wrist_jnt (str): wrist joint from internal data.
            fk_shoulder (str): fk shoulder control from internal data.
            fk_elbow (str): fk elbow control from internal data.
            fk_wrist (str): fk wrist control from internal data.            

        Returns:
            bool: True if successful, False otherwise.
        """

        # HOW TO FIX IT!
        # zero out control first, return both ik and fk to the same position
        # change rotate order on fk controls (same as joints)
        # reposition the control (ik)
        # run tool

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
                return False # forfeit operation (fix rotate order first)

        return True # still execute operation

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
        if not self.validate_switch_data("space switch"):
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
                        double_warning("No keys to bake!")
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

        # return to given frame and apply original matrix
        cmds.currentTime(frame, edit=True)
        cmds.setAttr(target_space, target_value)
        cmds.setKeyframe(target_space)
        apply_world_matrix(ctl, pos, rot)
        create_transform_keys(objects=[ctl], tx=True, ty=True, tz=True,
                              rx=True, ry=True, rz=True)

    def ikfk_switch(self):
        """Decides which ikfk operation to wrong based on user settings.

        TODO: check what happen if user have other space switch in between
              the set time range.

        TODO: too long at the moment, figure out a way to break this method up.
        """
        # check internal data to make sure user did not remove or rename stuffs
        # from the scene randomly 
        if not self.validate_switch_data("ikfk switch"):
            double_warning(
                "Either joints, controls or attributes loaded are invalid!"
                "\nPlease read the tooltip of each button for instruction."
            )
            return

        # TODO: any vis attr should be extra since some rigs already include that in the switch attr
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

        # get the flag: True --> ikfk, False --> fkik
        flag = self._ik_to_fk_radbtn.isChecked()
        if flag: # ikfk
            # check rotate order of the fk controls
            response = self._check_fk_rotate_order(shoulder_jnt, elbow_jnt,
                                                   wrist_jnt, fk_shoulder,
                                                   fk_elbow, fk_wrist)
            if response is False:
                # forfeit operation (fix rotate order first)
                return
            ctls = [ik_elbow, ik_wrist]

        else: # fkik
            ctls = [fk_shoulder, fk_elbow, fk_wrist]

        # get_ik_to_fk_switch(shoulder_jnt, elbow_jnt, wrist_jnt)
        # set_ik_to_fk_switch(fk_shoulder, fk_elbow, fk_wrist,
        #                     should_rot, elbow_rot, wrist_rot, fk_switch_attr,
        #                     fk_switch_value, fk_vis_attr, fk_vis_value,
        #                     ik_vis_attr, ik_vis_value, frame, prev_frame=None)

        # get_fk_to_ik_switch(shoulder_jnt, elbow_jnt, wrist_jnt,
        #                     ik_wrist)

        # set_fk_to_ik_switch(ik_wrist, ik_elbow, wrist_pos, wrist_rot,
        #                     elbow_pos, ik_switch_attr, ik_switch_value,
        #                     fk_vis_attr, fk_vis_value, ik_vis_attr,
        #                     ik_vis_value, frame, prev_frame=None)

        # cmds.undoInfo(openChunk=True)
        # lock_viewport()
        # # huge try block is used here to take care of undo chunk
        # # TODO: replace it using decorator
        # try: 
        if self._currentFrame_radbtn.isChecked():
            # doing one frame switch operation
            self.set_ikfk_switch(flag, shoulder_jnt, elbow_jnt, wrist_jnt,
                                 fk_shoulder, fk_elbow, fk_wrist,
                                 fk_switch_attr, fk_switch_value,
                                 fk_vis_attr, fk_vis_value, ik_vis_attr,
                                 ik_vis_value, ik_switch_attr,
                                 ik_switch_value, ik_wrist, ik_elbow,
                                 current_frame, prev_frame)

        else:
            range_start = int(self._start_frame_field.text())
            range_end = int(self._end_frame_field.text())
            keyframes = cmds.keyframe(ctls, query=True, timeChange=True)
            if keyframes is None:
                keyframes = [] # set to empty list instead
            keyframes = list(set(keyframes)) # rid of duplicates
            keyframes.sort()

            if self._bakeKeyframes_radbtn.isChecked(): # bake at keyframes
                ref_keys = keyframes[:] # save if for reference
                if self._set_time_range_chkbx.isChecked():
                    # only get the keys within set range
                    new_keys = []
                    for k in keyframes:
                        if range_start <= k <= range_end:
                            new_keys.append(k)
                    keyframes = new_keys

                if not keyframes:
                    double_warning("No keys to bake!")
                    # raise Exception # escape the block
                    return # for now

                # gathering data
                matrixData = []
                for key in keyframes:
                    cmds.currentTime(key, edit=True)
                    # cmds.setAttr(source_space, source_value)
                    # cmds.setKeyframe(source_space)
                    data = self.get_ikfk_data(flag, shoulder_jnt,
                                              elbow_jnt, wrist_jnt,
                                              ik_wrist, ik_switch_attr,
                                              ik_switch_value)
                    matrixData.append(data)

                # review
                for i, key in enumerate(keyframes):
                    a, b, c = matrixData[i]
                    print key
                    print a
                    print b
                    print c
                    print
                return

                # check if closing swap will run, if so, go reverse direction
                if len(keyframes) > 1 and keyframes[-1] < ref_keys[-1]:
                    cmds.currentTime(keyframes[-1], edit=True)
                    end_data = self.get_ikfk_data(not flag, shoulder_jnt,
                                                  elbow_jnt, wrist_jnt,
                                                  ik_wrist, ik_switch_attr,
                                                  ik_switch_value)
                    
                    # this may or may not be key so we have to be sure
                    # go to previous frame of the closing switch
                    # and save data
                    cmds.currentTime(keyframes[-1] - 1, edit=True)
                    prev_data = self.get_ikfk_data(flag, shoulder_jnt,
                                                   elbow_jnt, wrist_jnt,
                                                   ik_wrist, ik_switch_attr,
                                                   ik_switch_value)

                # start the operation
                if keyframes[0] > ref_keys[0]:
                    # self.set_space_switch(keyframes[0], ctl,
                    #                       source_space, source_value,
                    #                       target_space, target_value,)

                    self.set_ikfk_switch(flag, shoulder_jnt, elbow_jnt,
                                         wrist_jnt, fk_shoulder, fk_elbow,
                                         fk_wrist, fk_switch_attr,
                                         fk_switch_value, fk_vis_attr,
                                         fk_vis_value, ik_vis_attr,
                                         ik_vis_value, ik_switch_attr,
                                         ik_switch_value, ik_wrist,
                                         ik_elbow, keyframes[0],
                                         keyframes[0] - 1)

                    # remove first keyframe from data
                    keyframes = keyframes[1:]
                    matrixData = matrixData[1:]

                # make sure keyframes is not emptied from the first check
                if keyframes and keyframes[-1] < ref_keys[-1]:
                    # flip target and source to close chunk
                    # cannot use set_space_switch method since
                    # current matrix has already been changed so restore them
                    if flag: # ikfk
                        frame = keyframes[-1] # last frame
                        wrist_pos, wrist_rot, elbow_pos = end_data
                        self.set_fk_to_ik_switch(ik_wrist, ik_elbow, wrist_pos,
                                            wrist_rot, elbow_pos,
                                            ik_switch_attr,
                                            ik_switch_value, fk_vis_attr,
                                            fk_vis_value, ik_vis_attr,
                                            ik_vis_value, frame)

                        should_rot, elbow_rot, wrist_rot = prev_data
                        self.set_ik_to_fk_switch(fk_shoulder, fk_elbow,
                                            fk_wrist, should_rot,
                                            elbow_rot, wrist_rot,
                                            fk_switch_attr,
                                            fk_switch_value, fk_vis_attr,
                                            fk_vis_value, ik_vis_attr,
                                            ik_vis_value, frame)                        

                    else: # fkik
                        frame = keyframes[-1] - 1
                        should_rot, elbow_rot, wrist_rot = end_data
                        self.set_ik_to_fk_switch(fk_shoulder, fk_elbow,
                                            fk_wrist, should_rot,
                                            elbow_rot, wrist_rot,
                                            fk_switch_attr,
                                            fk_switch_value, fk_vis_attr,
                                            fk_vis_value, ik_vis_attr,
                                            ik_vis_value, frame)

                        wrist_pos, wrist_rot, elbow_pos = end_data
                        self.set_fk_to_ik_switch(ik_wrist, ik_elbow, wrist_pos,
                                            wrist_rot, elbow_pos,
                                            ik_switch_attr,
                                            ik_switch_value, fk_vis_attr,
                                            fk_vis_value, ik_vis_attr,
                                            ik_vis_value, frame)

                    # remove last keyframe from data
                    keyframes = keyframes[:-1]
                    matrixData = matrixData[:-1]

                # anything right on top or outside will run regularly
                # anything on the insde will make a set_space_switch
                # inside or outside refers to the outermost two keys
                for i, key in enumerate(keyframes):
                    if flag: # ikfk
                        should_rot, elbow_rot, wrist_rot = matrixData[i]
                        self.set_ik_to_fk_switch(fk_shoulder, fk_elbow,
                                            fk_wrist, should_rot,
                                            elbow_rot, wrist_rot,
                                            fk_switch_attr,
                                            fk_switch_value, fk_vis_attr,
                                            fk_vis_value, ik_vis_attr,
                                            ik_vis_value, key)                        

                    else: # fkik
                        wrist_pos, wrist_rot, elbow_pos = matrixData[i]
                        self.set_fk_to_ik_switch(ik_wrist, ik_elbow, wrist_pos,
                                            wrist_rot, elbow_pos,
                                            ik_switch_attr,
                                            ik_switch_value, fk_vis_attr,
                                            fk_vis_value, ik_vis_attr,
                                            ik_vis_value, key)

            # section for 'bake every frame'
            # TODO: check situations when keyframes is [] or 1-2 items
            else: # self._everyFrame_radbtn_radbtn.isChecked()
                if not self._set_time_range_chkbx.isChecked():
                    range_start, range_end, frame_range = (
                        get_timeline_range()
                    )
                time_range = range(int(range_start),
                                   int(range_end) + 1)

                # time_range size will always be 2 or more so skip checking
                # gathering data
                matrixData = []
                for key in keyframes:
                    cmds.currentTime(key, edit=True)
                    # cmds.setAttr(source_space, source_value)
                    # cmds.setKeyframe(source_space)
                    data = self.get_ikfk_data(flag, shoulder_jnt,
                                              elbow_jnt, wrist_jnt,
                                              ik_wrist, ik_switch_attr,
                                              ik_switch_value)
                    matrixData.append(data)

                # review
                for i, key in enumerate(keyframes):
                    a, b, c = matrixData[i]
                    print key
                    print a
                    print b
                    print c
                    print
                return


                if keyframes[0] < time_range[0]:
                    # self.set_space_switch(time_range[0], ctl,
                    #                       source_space, source_value,
                    #                       target_space, target_value,)
                    self.set_ikfk_switch(flag, shoulder_jnt, elbow_jnt,
                                         wrist_jnt, fk_shoulder, fk_elbow,
                                         fk_wrist, fk_switch_attr,
                                         fk_switch_value, fk_vis_attr,
                                         fk_vis_value, ik_vis_attr,
                                         ik_vis_value, ik_switch_attr,
                                         ik_switch_value, ik_wrist,
                                         ik_elbow, time_range[0],
                                         time_range[0] - 1)
                    time_range = time_range[1:]
                    matrixData = matrixData[1:]

                if keyframes[-1] > time_range[-1]:
                    # self.set_space_switch(time_range[-1], ctl,
                    #                       target_space, target_value,
                    #                       source_space, source_value,)
                    self.set_ikfk_switch(not flag, shoulder_jnt, elbow_jnt,
                                         wrist_jnt, fk_shoulder, fk_elbow,
                                         fk_wrist, fk_switch_attr,
                                         fk_switch_value, fk_vis_attr,
                                         fk_vis_value, ik_vis_attr,
                                         ik_vis_value, ik_switch_attr,
                                         ik_switch_value, ik_wrist,
                                         ik_elbow, time_range[-1],
                                         time_range[-1] - 1)                    
                    time_range = time_range[:-1]
                    matrixData = matrixData[:-1]

                for i, key in enumerate(time_range):
                    if flag: # ikfk
                        should_rot, elbow_rot, wrist_rot = matrixData[i]
                        self.set_ik_to_fk_switch(fk_shoulder, fk_elbow,
                                            fk_wrist, should_rot,
                                            elbow_rot, wrist_rot,
                                            fk_switch_attr,
                                            fk_switch_value, fk_vis_attr,
                                            fk_vis_value, ik_vis_attr,
                                            ik_vis_value, key)                        

                    else: # fkik
                        wrist_pos, wrist_rot, elbow_pos = matrixData[i]
                        self.set_fk_to_ik_switch(ik_wrist, ik_elbow, wrist_pos,
                                            wrist_rot, elbow_pos,
                                            ik_switch_attr,
                                            ik_switch_value, fk_vis_attr,
                                            fk_vis_value, ik_vis_attr,
                                            ik_vis_value, key)

            # return to current frame
            cmds.currentTime(current_frame, edit=True)

        # except Exception, e:
        #     double_warning(
        #         "There is an Error in try block!\n{}".format(str(e))
        #     )

        # finally: # clean up
        #     unlock_viewport()
        #     cmds.undoInfo(closeChunk=True)

    def get_ik_to_fk_switch(self, shoulder_jnt, elbow_jnt, wrist_jnt):
        """Executes the main ik --> fk switch operation using internal data.

        TODO: some rigs have separate visibility control (like FS rigs), some incorporate
              in the ikfk switch (like Caroline, and max I guess, which has both options),
              so far we make it work for Caronline, but need to think of a solution for this.
        """
        # get joint position and rotation in world space
        shoulder_pos, should_rot = get_world_matrix(shoulder_jnt)
        elbow_pos, elbow_rot = get_world_matrix(elbow_jnt)
        wrist_pos, wrist_rot = get_world_matrix(wrist_jnt)

        return should_rot, elbow_rot, wrist_rot # position not needed for FK

    def set_ik_to_fk_switch(self, fk_shoulder, fk_elbow, fk_wrist,
                            should_rot, elbow_rot, wrist_rot, fk_switch_attr,
                            fk_switch_value, fk_vis_attr, fk_vis_value,
                            ik_vis_attr, ik_vis_value, frame, prev_frame=None):
        """Executes the main ik --> fk switch operation using internal data.

        TODO: some rigs have separate visibility control (like FS rigs), some incorporate
              in the ikfk switch (like Caroline, and max I guess, which has both options),
              so far we make it work for Caronline, but need to think of a solution for this.
        """
        if prev_frame:
            # go to previous frame and hold down the value        
            cmds.currentTime(prev_frame, edit=True)
            for fk in [fk_shoulder, fk_elbow, fk_wrist]:
                # hold down previous position     
                create_transform_keys(objects=[fk], rx=True, ry=True, rz=True)
            cmds.setKeyframe(fk_switch_attr)
            cmds.setKeyframe(fk_vis_attr)
            cmds.setKeyframe(ik_vis_attr)

        # return to given frame
        cmds.currentTime(frame, edit=True)
        cmds.setAttr(fk_switch_attr, fk_switch_value)
        cmds.setKeyframe(fk_switch_attr)
        # cmds.setAttr(fk_vis_attr, int(fk_vis_value))
        # cmds.setKeyframe(fk_vis_attr)
        # cmds.setAttr(ik_vis_attr, int(ik_vis_value)) # does not work for some set up like Caroline
        # cmds.setKeyframe(ik_vis_attr)

        for fk, value in [[fk_shoulder, should_rot], [fk_elbow, elbow_rot],
                          [fk_wrist, wrist_rot]]:
            # apply in world space
            cmds.xform(fk, rotation=value, worldSpace=True)
            create_transform_keys(objects=[fk], rx=True, ry=True, rz=True)

    def get_fk_to_ik_switch(self, shoulder_jnt, elbow_jnt, wrist_jnt,
                            ik_wrist, ik_switch_attr, ik_switch_value):
        """Executes the main fk --> ik switch operation using internal data.

        TODO: for some rigs (max), the wrist flips when doing FK --> IK, and
              for some weird reason, apply matrix twice fixes it (close enough).
              best to find out what happen here

        TODO: some rigs have separate visibility control (like FS rigs), some incorporate
              in the ikfk switch (like Caroline, and max I guess, which has both options),
              so far we make it work for Caronline, but need to think of a solution for this.
        """
        # get joint position and rotation in world space
        orig_shoulder_pos, orig_should_rot = get_world_matrix(shoulder_jnt)
        orig_elbow_pos, orig_elbow_rot = get_world_matrix(elbow_jnt)
        orig_wrist_pos, orig_wrist_rot = get_world_matrix(wrist_jnt)
        orig_switch_value = cmds.getAttr(ik_switch_attr)

        # new way of getting wrist matrix (use constraint over xform)
        # for some weird reason the wrist flip (for rig Max)
        # but executing twice get it closer somehow (flip it back?)
        # this may not happen to all the rig (worked just fine on Caroline)
        # the wrist_pos should remain unchanged (verify??)
        wrist_pos, wrist_rot = constrain_move_key(wrist_jnt, ik_wrist,
                                                  'parentConstraint')
        cmds.setAttr(ik_switch_attr, ik_switch_value)  
        apply_world_matrix(ik_wrist, wrist_pos, wrist_rot) # apply in world space        
        # get joint position and rotation in world space, again
        wrist_pos, wrist_rot = constrain_move_key(wrist_jnt, ik_wrist,
                                                  'parentConstraint')
        # TODO: find out why. Could it be rotate order?

        # restore original matrix
        apply_world_matrix(ik_wrist, orig_wrist_pos, orig_wrist_rot)
        cmds.setAttr(ik_switch_attr, orig_switch_value)

        # vector math
        shoulder_jnt_vector = om.MVector(orig_shoulder_pos)
        elbow_jnt_vector = om.MVector(orig_elbow_pos)
        wrist_jnt_vector = om.MVector(orig_wrist_pos)
        midpoint_vector = ((wrist_jnt_vector - shoulder_jnt_vector) * 0.5
                           + shoulder_jnt_vector)
        aim_vector = ((elbow_jnt_vector - midpoint_vector) * 4
                      + midpoint_vector)
        new_elbow_pos = (aim_vector.x, aim_vector.y, aim_vector.z)

        return wrist_pos, wrist_rot, new_elbow_pos

    def set_fk_to_ik_switch(self, ik_wrist, ik_elbow, wrist_pos, wrist_rot,
                            elbow_pos, ik_switch_attr, ik_switch_value,
                            fk_vis_attr, fk_vis_value, ik_vis_attr,
                            ik_vis_value, frame, prev_frame=None):
        """Executes the main fk --> ik switch operation using internal data.

        TODO: for some rigs (max), the wrist flips when doing FK --> IK, and
              for some weird reason, apply matrix twice fixes it (close enough).
              best to find out what happen here

        TODO: some rigs have separate visibility control (like FS rigs), some incorporate
              in the ikfk switch (like Caroline, and max I guess, which has both options),
              so far we make it work for Caronline, but need to think of a solution for this.
        """
        if prev_frame:        
            # go to previous frame and hold down the value           
            cmds.currentTime(prev_frame, edit=True)
            create_transform_keys(objects=[ik_wrist],
                                  tx=True, ty=True, tz=True,
                                  rx=True, ry=True, rz=True)   
            create_transform_keys(objects=[ik_elbow],
                                  tx=True, ty=True, tz=True)
            cmds.setKeyframe(ik_switch_attr)
            cmds.setKeyframe(ik_vis_attr)
            cmds.setKeyframe(fk_vis_attr)

        # return to given frame
        cmds.currentTime(frame, edit=True)
        cmds.setAttr(ik_switch_attr, ik_switch_value)
        cmds.setKeyframe(ik_switch_attr)
        # cmds.setAttr(ik_vis_attr, int(ik_vis_value))
        # cmds.setKeyframe(ik_vis_attr)
        # cmds.setAttr(fk_vis_attr, int(fk_vis_value)) # does not work for some set up like Caroline
        # cmds.setKeyframe(fk_vis_attr)
        
        # process wrist
        apply_world_matrix(ik_wrist, wrist_pos, wrist_rot) # apply in world space         
        create_transform_keys(objects=[ik_wrist],
                              tx=True, ty=True, tz=True,
                              rx=True, ry=True, rz=True)

        # process elbow
        cmds.xform(ik_elbow, translation=elbow_pos, worldSpace=True)
        create_transform_keys(objects=[ik_elbow],
                              tx=True, ty=True, tz=True)

    def get_ikfk_data(self, flag, shoulder_jnt, elbow_jnt, wrist_jnt, ik_wrist, 
                      ik_switch_attr, ik_switch_value):
        """Decides which ikfk operation to wrong based on user settings.

        TODO: check what happen if user have other space switch in between
              the set time range.

        TODO: too long at the moment, figure out a way to break this method up.
        """
        if flag: # ikfk
            should_rot, elbow_rot, wrist_rot = (
                self.get_ik_to_fk_switch(shoulder_jnt, elbow_jnt,
                                         wrist_jnt)
            )
            return should_rot, elbow_rot, wrist_rot
        
        else: # fkik
            wrist_pos, wrist_rot, elbow_pos = (
                self.get_fk_to_ik_switch(shoulder_jnt, elbow_jnt, wrist_jnt,
                                         ik_wrist, ik_switch_attr,
                                         ik_switch_value)
            )
            return wrist_pos, wrist_rot, elbow_pos

    def set_ikfk_switch(self, flag, shoulder_jnt, elbow_jnt, wrist_jnt,
                        fk_shoulder, fk_elbow, fk_wrist, fk_switch_attr,
                        fk_switch_value, fk_vis_attr, fk_vis_value,
                        ik_vis_attr, ik_vis_value, ik_switch_attr,
                        ik_switch_value, ik_wrist, ik_elbow, frame,
                        prev_frame):
        """Decides which ikfk operation to wrong based on user settings.

        TODO: check what happen if user have other space switch in between
              the set time range.

        TODO: too long at the moment, figure out a way to break this method up.
        """
        if flag: # ikfk
            should_rot, elbow_rot, wrist_rot = self.get_ik_to_fk_switch(
                shoulder_jnt, elbow_jnt, wrist_jnt
            )
            self.set_ik_to_fk_switch(fk_shoulder, fk_elbow, fk_wrist,
                                     should_rot, elbow_rot, wrist_rot,
                                     fk_switch_attr, fk_switch_value,
                                     fk_vis_attr, fk_vis_value, ik_vis_attr,
                                     ik_vis_value, frame, prev_frame)
        else: # fkik
            wrist_pos, wrist_rot, elbow_pos = self.get_fk_to_ik_switch(
                shoulder_jnt, elbow_jnt, wrist_jnt, ik_wrist, ik_switch_attr,
                ik_switch_value
            )
            self.set_fk_to_ik_switch(ik_wrist, ik_elbow, wrist_pos, wrist_rot,
                                     elbow_pos, ik_switch_attr,
                                     ik_switch_value, fk_vis_attr,
                                     fk_vis_value, ik_vis_attr, ik_vis_value,
                                     frame, prev_frame)

    def mouseReleaseEvent(self, event):
        """Makes sure when user clicks on the UI it will set UI in focus.

        TODO: there should be a better way to implement this, like re-define
              the way QLineEdit behave.
        """
        super(SpaceSwitchTool, self).mouseReleaseEvent(event)
        self.setFocus()


if __name__ == "__main__":
    open_UI()

"""
import sys
path = "C:\\Users\\Danny Hsu\\Desktop\\animTools\\space_switch_tool"

if path not in sys.path:
    sys.path.append(path)
    
import spaceSwitch_tool_v015_DH as amt
reload(amt)

mayaPtr = amt.get_maya_window()
win = amt.SpaceSwitchTool(mayaPtr)
win.show()

"""