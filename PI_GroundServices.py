'''

X-Plane Ground Services

Copyright (C) 2011  Joan Perez i Cauhe
---
This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
'''

from XPLMDefs import *
from XPLMProcessing import *
from XPLMDataAccess import *
from XPLMUtilities import *
from XPLMPlanes import *
from SandyBarbourUtilities import *
from PythonScriptMessaging import *
from XPLMPlugin import *
from XPLMMenus import *
from XPWidgetDefs import *
from XPWidgets import *
from XPStandardWidgets import *
from XPLMScenery import *
from XPLMDisplay import *
from os import path
from random import randint
from math import *
import cPickle

# False constants
VERSION='ALPHA-1'
PRESETS_FILE='WFprofiles.wfp'
HELP_CAPTION='Profile name: '

# Conversion rates
LB2KG=0.45359237
KG2LB=2.20462262
L2GAL=0.264172052
GAL2LIT=3.78541178

# Uncomment the following line switch to the great metric system.
#LB2KG, KG2LB = 1,1

# ARBS 4600 l/min
#RFLOW=1200
# basket 1300k/min 2800 lb/min 1600 litres/min
#RFLOW=420

#Truck
RFLOW=900.0

#Callback interval
CINTERVAL=0.2

# Animation rate
ANIM_RATE=0.04

# l/kg
JETADENSITY=0.8


#Flow in kg/min
RFLOW=RFLOW*GAL2LIT*JETADENSITY

# Scenery Objects
TRUCK_OBJ='Custom Scenery/OpenSceneryX/objects/airport/vehicles/fuel/medium/%i/object.obj' % randint(1,9)
TUG_OBJ='Custom Scenery/OpenSceneryX/objects/airport/vehicles/tugs/large/%i/object.obj' % randint(1,4)
STAIR_OBJ='Custom Scenery/OpenSceneryX/objects/airport/vehicles/stairs/1/object.obj'
BUS_OBJ='Custom Scenery/OpenSceneryX/objects/airport/vehicles/busses_coaches/minibusses/swissport/1/object.obj'
GPU_OBJ='Custom Scenery/OpenSceneryX/objects/airport/vehicles/gpus/1/object.obj'

#Tug rudder offset
TUG_OFFSET=4.2

#
# Datarefs to store 
#
# Modify the following dict to add more datarefs to store in your profiles
#
DATAREFS = {
            'Payload':      'sim/flightmodel/weight/m_fixed',
            'Fuel tanks':   'sim/flightmodel/weight/m_fuel[0:9]',
            'jettison':     'sim/flightmodel/weight/m_jettison',
            'JATO':         'sim/flightmodel/misc/jato_left'
            }

class PythonInterface:
    def XPluginStart(self):
        self.Name = "GroundServices - " + VERSION
        self.Sig = "GroundServices.joanpc.PI"
        self.Desc = "X-Plane Ground Services"
        
        # Array of presets
        self.presets = []
        self.presetFile = False
        
        self.window, self.fuelWindow, self.reFuelWindow = False, False, False
        
        self.Mmenu = self.mainMenuCB
        
        self.mPluginItem = XPLMAppendMenuItem(XPLMFindPluginsMenu(), 'Ground Services', 0, 1)
        self.mMain       = XPLMCreateMenu(self, 'Ground Services', XPLMFindPluginsMenu(), self.mPluginItem, self.Mmenu, 0)
        
        # Menu Items
        self.mReFuel    =  XPLMAppendMenuItem(self.mMain, 'Request Refuel', 1, 1)
        self.mPushBack  =  XPLMAppendMenuItem(self.mMain, 'Request Pushback', 2, 1)
        self.mPushBack  =  XPLMAppendMenuItem(self.mMain, 'Request Stairs', 3, 1)
        self.mGpu       =  XPLMAppendMenuItem(self.mMain, 'GPU', 4, 1)
        
        self.tailnum = ''
        
        self.values = {}
        
        # Init datarefs
        for key in DATAREFS: self.values[key] = EasyDref(DATAREFS[key])
        
        # Init fuel datarefs 
        self.fuel = self.values['Fuel tanks']
        self.drPayLoad = self.values['Payload']
        self.drNFuelTanks = EasyDref('sim/aircraft/overflow/acf_num_tanks(int)')
        
        # Main floop
        self.floop = self.floopCallback
        XPLMRegisterFlightLoopCallback(self, self.floop, 0, 0)
        
        # Push back callback
        self.PushbackCB = self.pushBackCallback
        XPLMRegisterFlightLoopCallback(self, self.PushbackCB, 0, 0)
        
        self.acf = AircrafPosition()
        
        # Scenery objects
        self.pos , self.truck, self.tug, self.stairs, self.bus, self.gpu = tuple([False]) * 6
        
        self.stairStatus, self.gpuStatus = False, False

        return self.Name, self.Sig, self.Desc

    def destroyObjects(self):
        # Destroy all objects
        SceneryObject.destroyAll()
        self.pos , self.truck, self.tug, self.stairs, self.bus, self.gpu = tuple([False]) * 6

    def XPluginStop(self):
        self.destroyObjects()
        XPLMUnregisterFlightLoopCallback(self, self.floop, 0)
        XPLMDestroyMenu(self, self.mMain)
        if (self.reFuelWindow):
            XPDestroyWidget(self, self.FuelWindowWidget, 1)
        pass
        
    def XPluginEnable(self):
        return 1
    
    def XPluginDisable(self):
        pass
    
    def XPluginReceiveMessage(self, inFromWho, inMessage, inParam):
        if (inFromWho == XPLM_PLUGIN_XPLANE):
            if (inFromWho == XPLM_PLUGIN_XPLANE and inParam == XPLM_PLUGIN_XPLANE):# On aircraft change
                self.destroyObjects()
                self.CancelRefuel()
                # Destroy refuel window
                if self.reFuelWindow:
                    XPDestroyWidget(self, self.ReFuelWindowWidget, 1)
                    self.reFuelWindow = False
                self.tailnum = self.acf.tailNumber.value[0]
            # On plane load
            if (inParam == XPLM_PLUGIN_XPLANE and inMessage == XPLM_MSG_AIRPORT_LOADED ): # On aiport load
                self.destroyObjects()
                plane, plane_path = XPLMGetNthAircraftModel(0)
        
    def mainMenuCB(self, menuRef, menuItem):
        '''
        Main menu Callback
        '''
        if menuItem == 1:
            self.fuelTruck('come')
            if (not self.reFuelWindow):
                 self.CreateReFuelWindow(221, 640, 220, 75)
                 self.reFuelWindow = True
            elif (not XPIsWidgetVisible(self.ReFuelWindowWidget)):
                  XPShowWidget(self.ReFuelWindowWidget)
        elif menuItem == 2:
            ## Pushback
            # Clear other actions
            objects = [self.fuelTruck, self.stairsC, self.gpuTruck]
            for obj in objects: obj('go')
                 
            self.tugTruck('come')
            self.tug.animEndCallback = self.pushBack
        elif menuItem == 3:
            if not self.stairStatus: 
                self.stairsC('come')
                self.stairStatus = True
            else:
                self.stairsC('go')
                self.stairStatus = False
        elif menuItem == 4:
            if not self.gpuStatus: 
                self.gpuTruck('come')
                self.gpuStatus = True
            else:
                self.gpuTruck('go')
                self.gpuStatus = False

    def CreateReFuelWindow(self, x, y, w, h):
        # Get number of fuel tanks
        self.nFuelTanks = self.drNFuelTanks.value
        
        x2 = x + w
        y2 = y - h - self.nFuelTanks * 20 
        Buffer = "Request Refuel"
        
        # Create the Main Widget window
        self.ReFuelWindowWidget = XPCreateWidget(x, y, x2, y2, 1, Buffer, 1,0 , xpWidgetClass_MainWindow)
        
        # Add Close Box decorations to the Main Widget
        XPSetWidgetProperty(self.ReFuelWindowWidget, xpProperty_MainWindowHasCloseBoxes, 1)
        
        self.reFuelTankInput = []
        
        # Draw tank input 
        for i in range(self.nFuelTanks):
            XPCreateWidget(x+20, y-46, x+40, y-54, 1, 'Tank ' + str(i+1), 0, self.ReFuelWindowWidget, xpWidgetClass_Caption)
            tankInput = XPCreateWidget(x+60, y-40, x+190, y-62, 1, "", 0, self.ReFuelWindowWidget, xpWidgetClass_TextField)
            XPSetWidgetProperty(tankInput, xpProperty_TextFieldType, xpTextEntryField)
            XPSetWidgetProperty(tankInput, xpProperty_Enabled, 1)
            y -= 20
            self.reFuelTankInput.append(tankInput)
        
        
        # Cancel button
        self.CancelReFuelButton = XPCreateWidget(x+140, y-50, x+200, y-62, 1, "Cancel", 0, self.ReFuelWindowWidget, xpWidgetClass_Button)
        XPSetWidgetProperty(self.CancelReFuelButton, xpProperty_ButtonType, xpPushButton)
        
        # Save button
        self.ReFuelButton = XPCreateWidget(x+140, y-50, x+200, y-62, 1, "Request", 0, self.ReFuelWindowWidget, xpWidgetClass_Button)
        XPSetWidgetProperty(self.ReFuelButton, xpProperty_ButtonType, xpPushButton)
        
        # Register our widget handler
        self.ReFuelWindowHandlerCB = self.ReFuelWindowHandler
        XPAddWidgetCallback(self, self.ReFuelWindowWidget, self.ReFuelWindowHandlerCB)
        
    def ReFuelWindowHandler(self, inMessage, inWidget, inParam1, inParam2):
        if (inMessage == xpMessage_CloseButtonPushed):
            if (self.reFuelWindow):
                XPHideWidget(self.ReFuelWindowWidget)
            if self.truck and not self.refuel:
                self.fuelTruck('go')
            return 1

        # Handle any button pushes
        if (inMessage == xpMsg_PushButtonPressed):

            if (inParam1 == self.ReFuelButton):
                
                data = []
                for i in range(self.nFuelTanks):
                    buff = []
                    XPGetWidgetDescriptor(self.reFuelTankInput[i], buff, 256)
                    data.append(self.float(buff[0]) * LB2KG)
                self.refuel = data
                
                XPHideWidget(self.ReFuelButton)
                XPShowWidget(self.CancelReFuelButton)
                
                if self.truck and not self.truck.visible:
                    self.truck.show()
                
                XPLMSpeakString('%s Starting refuel' % self.tailnum)
                XPLMSetFlightLoopCallbackInterval(self, self.floop, CINTERVAL, 0, 0)
                return 1
            if (inParam1 == self.CancelReFuelButton):
                XPLMSpeakString('%s Refueling canceled' % self.tailnum)
                self.CancelRefuel()
        return 0
    
    def floopCallback(self, elapsedMe, elapsedSim, counter, refcon):
        '''
        Refuel Callback
        '''
        if self.refuel and sum(self.refuel) > 0:
            #ignore first call
            if elapsedMe > CINTERVAL * 4: return CINTERVAL
            tank = self.fuel.value
            
            for i in range(len(self.refuel)):
                if self.refuel[i] > 0: 
                    break
                
            toFuel = RFLOW/60.0*elapsedMe
            if toFuel > self.refuel[i]: 
                toFuel = self.refuel[i]
            
            self.refuel[i]-= toFuel
            tank[i] += toFuel
            
            self.fuel.value = tank
            
            return CINTERVAL
        else:
            XPLMSpeakString('%s Refuelling compleated' % self.tailnum)
            self.CancelRefuel()
            return 0

    def pushBackCallback(self, elapsedMe, elapsedSim, counter, refcon):
        if (self.acf.pbrake.value):
            if (not self.pusbackWaitBrakes):
                XPLMSpeakString('%s Push back advorted' % self.tailnum)
                if self.tug:
                    self.tug.animEndCallback = False
                    self.tugTruck('go')
                return 0
            else:
                # wait for release
                return 1
        
        self.pusbackWaitBrakes = False
        
        # Accelerate aircraft
        if (self.acf.groundspeed.value < 1.2):
            a = radians(self.acf.psi.value) + 180 % 360
            h = 0.04
            self.acf.vx.value -= cos(a) * h
            self.acf.vz.value -= sin(a) * h
            
        # Stick tuck to aircraft
        if self.tug:
            gear = self.acf.getGearcCoord(0)
            
            psi = self.acf.rudder.value*1.4
            pos = self.acf.getPointAtHdg(TUG_OFFSET, psi, gear)
            
            self.tug.setPos(pos, True)
            self.tug.psi += psi
        return -1
    
    def CancelRefuel(self):
        self.refuel = False;
        if self.truck:
            self.fuelTruck('go')
        XPLMSetFlightLoopCallbackInterval(self, self.floop, 0, 0, 0)
        if self.reFuelWindow:
            XPHideWidget(self.CancelReFuelButton)
            XPShowWidget(self.ReFuelButton)
            
            
    def pushBack(self):
        if (self.acf.pbrake.value):
            XPLMSpeakString('%s Push back ready, please release park brakes' % self.tailnum)
        else:
            XPLMSpeakString('%s Starting pushback.' % self.tailnum)
        self.pusbackWaitBrakes = True
        XPLMSetFlightLoopCallbackInterval(self, self.PushbackCB, -1, 0, 0)
        pass

    def float(self, string):
        # try to convert to float or return 0
        try: 
            val = float(string)
        except ValueError:
            val = 0.0
        return val
    
    def fuelTruck(self, op):
        '''
        Controls Fuel truck
        '''
        if not self.truck:
            self.truck = SceneryObject(self, TRUCK_OBJ)
        
        init = self.acfP(84, 40)
        
        path = [(self.acfP(15, 7), 6),
                (self.acfP(12, 18), 2),
               ]
        backcourse = [(self.acfP(3, 28), 3), 
                      (init, 6)
                      ]
        if  op == 'come' != self.truck.lop:
            self.truck.setPos(init, True)
            self.truck.animate(path, False)
            self.truck.show()
        elif op == 'go' and self.truck.lop == 'come':
            self.truck.animate(backcourse, False)
        self.truck.lop = op
        
    def tugTruck(self, op):
        '''
        Controls Tug
        '''
        
        if not self.tug:
            self.tug = SceneryObject(self, TUG_OBJ)
                    
        y = self.acf.ly
        gear = self.acf.getGearcCoord()
        
        path = [ (self.acf.getPointAtHdg(6, 0, gear), 5),
                (self.acf.getPointAtHdg(10 + TUG_OFFSET, 0, gear), TUG_OFFSET),
                (gear, 5, self.acf.psi.value)
              ]
        backcourse = [(self.acf.getGearcCoord(10 + TUG_OFFSET) , 5),
                      (self.acf.getPointAtHdg(20, 45), 2),
                       (self.acf.getPointAtHdg(50, 94), 3),
                       (self.acf.getPointAtHdg(64, 130), 3)
                     ]
        
        if  op == 'come' != self.tug.lop:
            self.tug.setPos(self.acf.getPointAtHdg(100, 270), True)
            self.tug.psi = self.tug.getHeading(self.tug.getPos(), self.acf.get()) + 30 %360
            self.tug.animate(path, False)
            self.tug.show()
        elif op == 'go' != self.tug.lop == 'come':
            self.tug.animate(backcourse, False)
        self.tug.lop = op
    
    def acfP(self, x, z):
        'Shorcut for 2d points'
        return self.acf.getPointAtRel([x, 0.0, z, 0.0, 0.0])
    
    def stairsC(self, op):
        '''
        Controls Stairs
        '''
        
        if not self.stairs:
            self.stairs = SceneryObject(self, STAIR_OBJ)
        
        door = self.acf.getDoorCoord(0)
        hinv =  door[4] + 90%360
        
        init = self.acfP(-100, 40)
        
        path = [(self.acfP(-30, -20), 5),
                (self.acf.getPointAtHdg(5, hinv, door), 3),
                (door , 2, door[4]),
                ]
        
        backcourse = [(self.acf.getPointAtHdg(6, hinv, door), 3, door[4]),
                      (self.acfP(-30, -20), 5),
                      (init , 5),
                      ]
        
        if  op == 'come' != self.stairs.lop:
            self.stairs.setPos(init, True)
            self.stairs.show()
            self.stairs.animate(path, False)
            self.stairs.animEndCallback = self.buses
        elif op == 'go' and self.stairs.lop == 'come':
            if self.bus:
                self.bus.loop = False
            self.stairs.animate(backcourse, False)
        self.stairs.lop = op
    
    def buses(self):
        '''
        Controls buses
        '''
        if not self.bus:
            self.bus = SceneryObject(self, BUS_OBJ)
        
        door = self.acf.getDoorCoord(20)
        door2 = door[:]
        door2[2] += 4
        init = init = self.acfP(-80, 40)
        
        path = [(door , 5),
                (door2, 2),
                (door2, 20),
                (init, 5),
                (init, 20),
                ]
        
        self.bus.setPos(init, True)
        self.bus.show()
        self.bus.animate(path, False, True)
    
    def gpuTruck(self, op):
        '''
        Controls gpu truck
        '''
        if not self.gpu:
            self.gpu = SceneryObject(self, GPU_OBJ)
        
        init = init = self.acfP(80, 40)
        pos = self.acfP(2, 19)
        pos2 = self.acfP(12, 20)
        path = [(pos2 , 5),
                (pos, 2),
                ]
        backcourse = [(pos2 , 5),
                      (init, 5),
                      ]
        if op == 'come' != self.gpu.lop:
            self.gpu.setPos(init, True)
            self.gpu.show()
            self.gpu.animate(path, False)
        elif op == 'go'and self.gpu.lop  == 'come':
            self.gpu.animate(backcourse, False)
        self.gpu.lop = op
        
'''
Includes
'''
class AircrafPosition:
    '''
    Aircraft position and utilities
    '''
    def __init__(self):
        
        #Tail number
        self.tailNumber = EasyDref('sim/aircraft/view/acf_tailnum[0:40]', 'bit')
        
        # local position
        self.lx = EasyDref('sim/flightmodel/position/local_x', 'double')
        self.ly = EasyDref('sim/flightmodel/position/local_y', 'double')
        self.lz = EasyDref('sim/flightmodel/position/local_z', 'double')
        
        # Orientation
        self.q = EasyDref('sim/flightmodel/position/q[0:3]', 'float')
        
        self.theta   = EasyDref('sim/flightmodel/position/theta', 'float')
        self.psi     = EasyDref('sim/flightmodel/position/psi', 'float')
        self.phi     = EasyDref('sim/flightmodel/position/phi', 'float')
        
        # Velocity 
        self.vx = EasyDref('sim/flightmodel/position/local_vx', 'float')
        self.vy = EasyDref('sim/flightmodel/position/local_vy', 'float')
        self.vz = EasyDref('sim/flightmodel/position/local_vz', 'float')
        
        # acceleration
        self.ax = EasyDref('sim/flightmodel/position/local_ax', 'float')
        self.ay = EasyDref('sim/flightmodel/position/local_ay', 'float')
        self.az = EasyDref('sim/flightmodel/position/local_az', 'float')
        
        # brakes
        self.pbrake = EasyDref('sim/flightmodel/controls/parkbrake', 'float')
        
        # Ground speed
        self.groundspeed = EasyDref('sim/flightmodel/position/groundspeed', 'float')
        
        # Rudder deflection
        self.rudder = EasyDref('sim/flightmodel/controls/ldruddef', 'float')
        
        # Gear deflection
        self.gearHeading = EasyDref('sim/flightmodel2/gear/gear_heading_deg[0:3]', 'float')
        
        # Gear position
        #self.gear = EasyDref('sim/aircraft/parts/acf_gear_znodef[0:10]', 'float')
        #self.gear = EasyDref('sim/aircraft/parts/acf_Zarm[0:10]', 'float')
        self.gear = EasyDref('sim/flightmodel/parts/tire_z_no_deflection[0:10]', 'float')
        
        # Gpu
        self.gpuOn = EasyDref('sim/cockpit/electrical/gpu_on', 'int')
        self.gpuAmps = EasyDref('sim/cockpit/electrical/gpu_amps', 'float')
        
        # Door position
        self.doorX = EasyDref('sim/aircraft/view/acf_door_x', 'float')
        self.doorZ = EasyDref('sim/aircraft/view/acf_door_z', 'float')
        
    def get(self):
        # Return a position array suitable for Drawing
        return [self.lx.value, self.ly.value, self.lz.value, self.theta.value, self.psi.value, self.phi.value]
        pass
    
    def getGearcCoord(self, dist = TUG_OFFSET):
        h = self.gear.value
        h.sort()
        h = h[0]*-1 + dist #+ 2 # tug gear separation
        
        pos = self.getPointAtHdg(h)
        
        return pos
    
    def getDoorCoord(self, dist = 0):
        pos = [self.doorX.value, 0 ,self.doorZ.value, 0.0, 0.0]
        psi = 90
        if pos[0] > 0: psi = 270
        pos[0] -= dist * pos[0]**0
        pos = self.getPointAtRel(pos)
        pos[4] = self.psi.value +psi%360
        
        return pos

    def getPointAtHdg(self, dist, hdg = 0, orig = False):
        '''
        Return a point at a given distance and heading
        '''
        if not orig:
            orig = self.get()
            
        a = 90 + hdg + orig[4]
        h = dist
        x = cos(radians(a)) * h
        z = sin(radians(a)) * h
        
        orig = orig[:]
        orig[0] -= x * orig[0]**0
        orig[2] -= z * orig[2]**0
        
        return orig
    
    def getPointAtRel(self, pos, orig = False):
        p1 = self.getPointAtHdg(pos[0], 90, orig)
        return self.getPointAtHdg(pos[2], 0, p1)

class SceneryObject:
    '''
    Loads and draws an object in a specified position
    '''
    ProbeRef = XPLMCreateProbe(xplm_ProbeY)
    # Inventory
    objects = []
    drawing = False
    DrawCB = False
    
    def __init__(self, plugin, file, visible = False):
        SceneryObject.plugin = plugin
        
        # position
        self.x, self.y, self.z, = 0.0, 0.0, 0.0
        # orientation
        self.theta, self.psi, self.phi = 0.0, 0.0, 0.0
        
        # Queue
        self.queue = []
        # Backup queue for loops
        self._queue = []
        
        self.loop = False
        
        # visible?
        self.visible = visible
        self.floor = 1
        
        # load object
        self.object = XPLMLoadObject(file)
        
        self.lop = 'load'
        
        # Return false on error
        if not self.object:
           print "Can't open file: %s", file
           self.loaded = False
           return None
        
        self.loaded = True
        SceneryObject.objects.append(self) 
        
        self.animEndCallback = False
        
        if not self.drawing:
            SceneryObject.DrawCB = SceneryObject.DrawCallback
            XPLMRegisterDrawCallback(SceneryObject.plugin, SceneryObject.DrawCB, xplm_Phase_Objects, 0, 0)
            SceneryObject.drawing = True
        
        # Main floop
        self.floop = self.floopCallback
        XPLMRegisterFlightLoopCallback(SceneryObject.plugin, self.floop, 0, 0)
   
    def animate(self, queue, floor = True, loop = False):
        self._queue,  self.queue = queue[:], queue
        
        self.loop = loop
        
        next = self.queue.pop(0)
        if len(next) == 3:
            to, time, psi = next
            to[4] = psi
        else:
            to, time = next
            to[4] = self.getHeading(self.getPos(), to)
            
        self.MoveTo(to, time, floor)
    
    def getHeading(self, p1, p2):
        # Get heading from point to point
        res = [p2[0] - p1[0], p2[2] - p1[2]]
        
        if res[0] == 0:
            if  res[1] > 0: return 0
            else: return 180
        if res[1] == 0:
            if res[0] > 0: 90
            else: return 270
            
        h = (res[0]**2 + res[1]**2)**0.5
        hdg = fabs(degrees(asin(res[1]/h)))

        #quadrants
        if res[1] < 0:
            if res[0] > 0: hdg = 90 - hdg
            else: hdg = 270 + hdg 
        else:
            if res[0] > 0: hdg = 90 + hdg
            else: hdg = 270 - hdg
        
        return hdg
    
    def MoveTo(self, pos, time, floor = True):
        self.goTo = pos
        self.time = float(time)
        XPLMSetFlightLoopCallbackInterval(SceneryObject.plugin, self.floop, ANIM_RATE, 0, 0)    
    
    def floopCallback(self, elapsedMe, elapsedSim, counter, refcon):
        '''
        Cheap Animation callback
        '''
        if elapsedMe > ANIM_RATE * 2:
            return ANIM_RATE
        
        elif self.time > ANIM_RATE:
            pos = [self.x, self.y, self.z, self.theta, self.psi, self.phi]
            pos[0] += (self.goTo[0] - pos[0]) / self.time * ANIM_RATE
            #pos[1] += (self.goTo[1] - pos[1]) / self.time * ANIM_RATE
            pos[2] += (self.goTo[2] - pos[2]) / self.time * ANIM_RATE
            
            # Heading
            if pos[4] != self.goTo[4]:
                a = self.goTo[4] - pos[4]
                # Get shorter heading
                if abs(a) > 180: a = (360 - self.goTo[4] + pos[4]) * -1 %360
                
                tohd = a / self.time * ANIM_RATE * 4
                pos[4] += tohd
                pos[4] += 360 % 360
                            
            self.setPos(pos, True)
            self.time -= ANIM_RATE
            
            return ANIM_RATE
 
        # Enqueue next
        elif len(self.queue):
            next = self.queue.pop(0)
            if len(next) == 3:
                self.goTo, self.time, psi = next
                self.goTo[4] = psi
            else:
                self.goTo, self.time = next
                self.goTo[4] = self.getHeading(self.getPos(), self.goTo)

            return ANIM_RATE
        # end callback
        elif self.animEndCallback: 
            self.animEndCallback()
            return 0
        
        # loop
        elif self.loop: 
            self.queue = self._queue[:]
            return ANIM_RATE
        return 0
    
    @classmethod    
    def DrawCallback(self, inPhase, inIsBefore, inRefcon):
        '''
        Drawing callback
        '''
        for obj in self.objects: 
            pos = obj.x, obj.y, obj.z, obj.theta, obj.psi, obj.phi
            XPLMDrawObjects(obj.object, 1, [pos], 0, 0)
        return 1
    
    def setPos(self, pos, floor = False):
        '''
        Set position: floor = True to stick to the floor
        '''
        if floor:
            self.floor = 0
            info = []
            XPLMProbeTerrainXYZ(self.ProbeRef, pos[0], pos[1], pos[2], info)
            self.x, self.y, self.z = info[1], info[2] ,info[3]
            self.theta, self.psi, self.phi = pos[3], pos[4], pos[5]
        else:
             self.x, self.y, self.z, self.theta, self.psi, self.phi = tuple(pos)
    def getPos(self):
        return [self.x, self.y, self.z, self.theta, self.psi, self.phi]
    
    def hide(self):
        '''
        Hide object
        '''
        self.visible = False
    def show(self):
        '''
        Show object
        '''
        self.visible = True
    
    def destroy(self):
        '''
        Destroy object and callbacks
        '''
        SceneryObject.objects.remove(self)
        XPLMSetFlightLoopCallbackInterval(SceneryObject.plugin, self.floop, ANIM_RATE, 0, 0)    
        XPLMUnregisterFlightLoopCallback(SceneryObject.plugin, self.floop, 0)
        XPLMUnloadObject(self.object)
        self = False

    @classmethod
    def destroyAll(self):
        for obj in self.objects[:]:
            obj.destroy()
        if self.drawing:
            XPLMUnregisterDrawCallback(SceneryObject.plugin, self.DrawCB, xplm_Phase_Objects, 0, 0)
            self.drawing = False

class EasyDref:    
    '''
    Easy Dataref access
    
    Copyright (C) 2011  Joan Perez i Cauhe
    '''
    def __init__(self, dataref, type = "float"):
        # Clear dataref
        dataref = dataref.strip()
        self.isarray, dref = False, False
        
        if ('"' in dataref):
            dref = dataref.split('"')[1]
            dataref = dataref[dataref.rfind('"')+1:]
        
        if ('(' in dataref):
            # Detect embedded type, and strip it from dataref
            type = dataref[dataref.find('(')+1:dataref.find(')')]
            dataref = dataref[:dataref.find('(')] + dataref[dataref.find(')')+1:]
        
        if ('[' in dataref):
            # We have an array
            self.isarray = True
            range = dataref[dataref.find('[')+1:dataref.find(']')].split(':')
            dataref = dataref[:dataref.find('[')]
            if (len(range) < 2):
                range.append(range[0])
            
            self.initArrayDref(range[0], range[1], type)
            
        elif (type == "int"):
            self.dr_get = XPLMGetDatai
            self.dr_set = XPLMSetDatai
            self.cast = int
        elif (type == "float"):
            self.dr_get = XPLMGetDataf
            self.dr_set = XPLMSetDataf
            self.cast = float  
        elif (type == "double"):
            self.dr_get = XPLMGetDatad
            self.dr_set = XPLMSetDatad
            self.cast = float
        else:
            print "ERROR: invalid DataRef type", type
        
        if dref: dataref = dref
        self.DataRef = XPLMFindDataRef(dataref)
        if self.DataRef == False:
            print "Can't find " + dataref + " DataRef"
    
    def initArrayDref(self, first, last, type):
        self.index = int(first)
        self.count = int(last) - int(first) +1
        self.last = int(last)
        
        if (type == "int"):
            self.rget = XPLMGetDatavi
            self.rset = XPLMSetDatavi
            self.cast = int
        elif (type == "float"):
            self.rget = XPLMGetDatavf
            self.rset = XPLMSetDatavf
            self.cast = float  
        elif (type == "bit"):
            self.rget = XPLMGetDatab
            self.rset = XPLMSetDatab
            self.cast = float
        else:
            print "ERROR: invalid DataRef type", type
        pass

    def set(self, value):
        if (self.isarray):
            self.rset(self.DataRef, value, self.index, len(value))
        else:
            self.dr_set(self.DataRef, self.cast(value))
            
    def get(self):
        if (self.isarray):
            list = []
            self.rget(self.DataRef, list, self.index, self.count)
            return list
        else:
            return self.dr_get(self.DataRef)
        
    def __getattr__(self, name):
        if name == 'value':
            return self.get()
        else:
            raise AttributeError
    
    def __setattr__(self, name, value):
        if name == 'value':
            self.set(value)
        else:
            self.__dict__[name] = value