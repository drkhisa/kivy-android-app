from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.slider import Slider
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.togglebutton import ToggleButton
from kivy.clock import Clock
from kivy.core.window import Window

import json
import os
from threading import Thread

from jnius import autoclass, cast
from android import mActivity

CONFIG_FILE = "midi_config.json"
NUM_CHANNELS = 6

# Android MIDI API классы
MidiManager = autoclass("android.media.midi.MidiManager")
MidiDeviceInfo = autoclass("android.media.midi.MidiDeviceInfo")
MidiDeviceService = autoclass("android.media.midi.MidiDeviceService")
MidiReceiver = autoclass("android.media.midi.MidiReceiver")
MidiInputPort = autoclass("android.media.midi.MidiInputPort")
MidiOutputPort = autoclass("android.media.midi.MidiOutputPort")
MidiDevice = autoclass("android.media.midi.MidiDevice")
Context = autoclass("android.content.Context")
PythonActivity = autoclass("org.kivy.android.PythonActivity")
activity = PythonActivity.mActivity
midi_service = cast("android.media.midi.MidiManager", activity.getSystemService(Context.MIDI_SERVICE))


class Channel(BoxLayout):
    def __init__(self, index, app, **kwargs):
        super().__init__(orientation='vertical', spacing=5, padding=5, **kwargs)
        self.index = index
        self.app = app

        self.add_widget(Label(text=f"Канал {index + 1}", size_hint=(1, 0.1)))

        self.fader = Slider(min=0, max=127, value=64, orientation='vertical', size_hint=(1, 0.6))
        self.fader.bind(value=self.on_fader_change)
        self.add_widget(self.fader)

        self.mute = ToggleButton(text="Mute", size_hint=(1, 0.1), background_color=(1, 0, 0, 1))
        self.mute.bind(on_press=self.on_mute_toggle)
        self.add_widget(self.mute)

        self.pan = Slider(min=-64, max=63, value=0, orientation='horizontal', size_hint=(1, 0.1))
        self.pan.bind(value=self.on_pan_change)
        self.add_widget(self.pan)

        self.effect = Slider(min=0, max=127, value=0, orientation='horizontal', size_hint=(1, 0.1))
        self.effect.bind(value=self.on_effect_change)
        self.add_widget(self.effect)

        self.assign_btn = Button(text="Assign", size_hint=(1, 0.1))
        self.assign_btn.bind(on_press=self.open_assign_popup)
        self.add_widget(self.assign_btn)

    def on_fader_change(self, instance, value):
        if not self.mute.state == 'down':
            self.app.send_cc(f"fader_{self.index}", int(value))

    def on_mute_toggle(self, instance):
        state = self.mute.state == 'down'
        color = (0.5, 0.5, 0.5, 1) if state else (1, 0, 0, 1)
        self.mute.background_color = color
        val = 127 if state else 0
        self.app.send_cc(f"mute_{self.index}", val)
        if not state:
            self.app.send_cc(f"fader_{self.index}", int(self.fader.value))

    def on_pan_change(self, instance, value):
        self.app.send_cc(f"pan_{self.index}", int(value + 64))

    def on_effect_change(self, instance, value):
        self.app.send_cc(f"effect_{self.index}", int(value))

    def open_assign_popup(self, instance):
        self.app.enter_assign_mode(f"fader_{self.index}")


class MidiApp(App):
    def build(self):
        self.assigned_controls = {}
        self.channels = []
        self.compressor_state = False
        self.assigning_control = None
        self.midi_out_port = None
        self.midi_in_port = None
        self.saved_data = {}
        self.load_config()

        root = BoxLayout(orientation='vertical', padding=10, spacing=10)

        grid = GridLayout(cols=NUM_CHANNELS, spacing=10, size_hint=(1, 0.85))
        for i in range(NUM_CHANNELS):
            ch = Channel(i, self)
            self.channels.append(ch)
            grid.add_widget(ch)

        root.add_widget(grid)

        bottom = BoxLayout(size_hint=(1, 0.15), spacing=10)
        self.compressor_btn = Button(text="Компрессор", size_hint=(0.3, 1), background_color=(0.3, 0.3, 0.3, 1))
        self.compressor_btn.bind(on_press=self.toggle_compressor)
        bottom.add_widget(self.compressor_btn)

        assign_mode_btn = Button(text="Назначить MIDI", size_hint=(0.3, 1))
        assign_mode_btn.bind(on_press=lambda x: self.enter_assign_mode("compressor"))
        bottom.add_widget(assign_mode_btn)

        save_btn = Button(text="Сохранить", size_hint=(0.3, 1))
        save_btn.bind(on_press=lambda x: self.save_config())
        bottom.add_widget(save_btn)

        root.add_widget(bottom)

        self.connect_midi()
        return root

    def connect_midi(self):
        device_infos = midi_service.getDevices()
        if device_infos.length > 0:
            device_info = device_infos[0]
            midi_service.openDevice(device_info, self.on_midi_device_opened, None)

    def on_midi_device_opened(self, device):
        self.midi_out_port = device.openOutputPort(0)
        self.midi_in_port = device.openInputPort(0)

        def listen():
            while True:
                if self.midi_in_port:
                    buffer = bytearray(3)
                    n = self.midi_in_port.read(buffer, 0, 3)
                    if n >= 3:
                        status, cc, value = buffer[0], buffer[1], buffer[2]
                        if 0xB0 <= status <= 0xBF:
                            if self.assigning_control:
                                control_name = self.assigning_control
                                self.assigned_controls[control_name] = cc
                                self.assigning_control = None
                                self.save_config()
                                print(f"Assigned CC {cc} to {control_name}")
                            else:
                                # Обновляем UI в основном потоке
                                Clock.schedule_once(lambda dt: self.update_control_by_cc(cc, value))

        Thread(target=listen, daemon=True).start()

    def update_control_by_cc(self, cc, value):
        for control_name, assigned_cc in self.assigned_controls.items():
            if assigned_cc == cc:
                if control_name.startswith('fader_'):
                    index = int(control_name.split('_')[1])
                    if 0 <= index < len(self.channels):
                        self.channels[index].fader.value = value
                elif control_name.startswith('mute_'):
                    index = int(control_name.split('_')[1])
                    if 0 <= index < len(self.channels):
                        self.channels[index].mute.state = 'down' if value >= 64 else 'normal'
                        self.channels[index].on_mute_toggle(None)
                elif control_name.startswith('pan_'):
                    index = int(control_name.split('_')[1])
                    if 0 <= index < len(self.channels):
                        pan_val = value - 64
                        self.channels[index].pan.value = pan_val
                elif control_name.startswith('effect_'):
                    index = int(control_name.split('_')[1])
                    if 0 <= index < len(self.channels):
                        self.channels[index].effect.value = value
                elif control_name == 'compressor':
                    self.compressor_state = value >= 64
                    self.compressor_btn.background_color = (0, 0.8, 0, 1) if self.compressor_state else (0.3, 0.3, 0.3, 1)
                break

    def send_cc(self, control_name, value):
        cc = self.assigned_controls.get(control_name)
        if cc is not None and self.midi_out_port:
            data = bytearray([0xB0, cc, value])
            self.midi_out_port.send(data, 0, len(data))
            print(f"Sent CC {cc} = {value}")

    def toggle_compressor(self, instance):
        self.compressor_state = not self.compressor_state
        val = 127 if self.compressor_state else 0
        self.send_cc("compressor", val)
        if self.compressor_state:
            self.compressor_btn.background_color = (0, 0.8, 0, 1)
        else:
            self.compressor_btn.background_color = (0.3, 0.3, 0.3, 1)

    def save_config(self):
        data = {
            "assigned_controls": self.assigned_controls,
            "fader_values": [ch.fader.value for ch in self.channels],
            "pan_values": [ch.pan.value for ch in self.channels],
            "effect_values": [ch.effect.value for ch in self.channels],
            "mute_states": [ch.mute.state == 'down' for ch in self.channels],
            "compressor_state": self.compressor_state
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.assigned_controls = data.get("assigned_controls", {})
                    self.saved_data = data
            except:
                self.saved_data = {}
        else:
            self.saved_data = {}

    def on_start(self):
        if not hasattr(self, 'saved_data'):
            return
        data = self.saved_data
        for i, ch in enumerate(self.channels):
            if i < len(data.get("fader_values", [])):
                ch.fader.value = data["fader_values"][i]
            if i < len(data.get("pan_values", [])):
                ch.pan.value = data["pan_values"][i]
            if i < len(data.get("effect_values", [])):
                ch.effect.value = data["effect_values"][i]
            if i < len(data.get("mute_states", [])) and data["mute_states"][i]:
                ch.mute.state = 'down'
                ch.on_mute_toggle(None)

        self.compressor_state = data.get("compressor_state", False)
        if self.compressor_state:
            self.compressor_btn.background_color = (0, 0.8, 0, 1)

    def enter_assign_mode(self, control_name):
        self.assigning_control = control_name
        popup = Popup(title="Назначение MIDI CC", size_hint=(0.6, 0.4))
        popup.content = Label(text="Поверните контроллер или нажмите кнопку на MIDI устройстве")
        popup.open()
        Clock.schedule_once(lambda dt: popup.dismiss(), 3)


if __name__ == '__main__':
    Window.clearcolor = (0.15, 0.15, 0.15, 1)
    MidiApp().run()
