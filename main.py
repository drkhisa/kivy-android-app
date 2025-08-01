import json
import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.slider import Slider
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.button import Button
from kivy.uix.label import Label
from jnius import autoclass, cast

CONFIG_FILE = "midi_config.json"
NUM_CHANNELS = 6

# MIDI API
PythonActivity = autoclass('org.kivy.android.PythonActivity')
Context = autoclass('android.content.Context')
MidiManager = autoclass('android.media.midi.MidiManager')
MidiDeviceInfo = autoclass('android.media.midi.MidiDeviceInfo')
MidiReceiver = autoclass('android.media.midi.MidiReceiver')
MidiOutputPort = autoclass('android.media.midi.MidiOutputPort')

class MIDIController:
    def __init__(self):
        self.activity = PythonActivity.mActivity
        self.midi_manager = cast(MidiManager, self.activity.getSystemService(Context.MIDI_SERVICE))
        self.output_port = None
        self.open_output_port()

    def open_output_port(self):
        infos = self.midi_manager.getDevices()
        if len(infos) > 0:
            self.device = infos[0]  # по умолчанию первый
            self.midi_manager.openDevice(self.device, self.on_device_opened, None)

    def on_device_opened(self, device):
        if device is not None:
            self.output_port = device.openOutputPort(0)

    def send_cc(self, cc_num, value, channel=0):
        if self.output_port:
            status = 0xB0 | (channel & 0x0F)
            msg = bytearray([status, cc_num & 0x7F, value & 0x7F])
            self.output_port.send(msg, 0, len(msg))

class MixerChannel(BoxLayout):
    def __init__(self, channel_num, midi_ctrl, config, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.channel = channel_num
        self.midi = midi_ctrl
        self.config = config

        self.add_widget(Label(text=f"Канал {self.channel + 1}"))

        self.fader = Slider(min=0, max=127, value=self.config.get('fader', 0))
        self.fader.bind(value=self.on_fader_change)
        self.add_widget(Label(text="Громкость"))
        self.add_widget(self.fader)

        self.pan = Slider(min=0, max=127, value=self.config.get('pan', 64))
        self.pan.bind(value=self.on_pan_change)
        self.add_widget(Label(text="Панорама"))
        self.add_widget(self.pan)

        self.mute = ToggleButton(text="Mute", state='down' if self.config.get('mute') else 'normal')
        self.mute.bind(on_press=self.on_mute_toggle)
        self.add_widget(self.mute)

        self.fx = Slider(min=0, max=127, value=self.config.get('fx', 0))
        self.fx.bind(value=self.on_fx_change)
        self.add_widget(Label(text="FX"))
        self.add_widget(self.fx)

        self.cc_map = self.config.get('cc_map', {
            'fader': 10 + self.channel,
            'pan': 20 + self.channel,
            'mute': 30 + self.channel,
            'fx': 40 + self.channel,
        })

    def on_fader_change(self, instance, value):
        self.midi.send_cc(self.cc_map['fader'], int(value), self.channel)
        self.config['fader'] = int(value)

    def on_pan_change(self, instance, value):
        self.midi.send_cc(self.cc_map['pan'], int(value), self.channel)
        self.config['pan'] = int(value)

    def on_mute_toggle(self, instance):
        val = 0 if instance.state == 'down' else 127
        self.midi.send_cc(self.cc_map['mute'], val, self.channel)
        self.config['mute'] = instance.state == 'down'

    def on_fx_change(self, instance, value):
        self.midi.send_cc(self.cc_map['fx'], int(value), self.channel)
        self.config['fx'] = int(value)

class MidiCompressorButton(ToggleButton):
    def __init__(self, midi_ctrl, config, **kwargs):
        super().__init__(**kwargs)
        self.text = "Компрессор"
        self.midi = midi_ctrl
        self.config = config
        self.state = 'down' if config.get("compressor_state") else 'normal'
        self.background_color = (0, 1, 0, 1) if self.state == 'down' else (1, 1, 1, 1)
        self.bind(on_press=self.on_toggle)

    def on_toggle(self, instance):
        val = 127 if instance.state == 'down' else 0
        self.background_color = (0, 1, 0, 1) if instance.state == 'down' else (1, 1, 1, 1)
        self.config["compressor_state"] = instance.state == 'down'
        self.midi.send_cc(self.config.get("compressor_cc", 50), val, 0)

class MidiControllerApp(App):
    def build(self):
        self.config_data = self.load_config()
        self.midi = MIDIController()
        self.layout = BoxLayout(orientation='horizontal')

        self.channels = []
        for i in range(NUM_CHANNELS):
            chan_config = self.config_data.setdefault(f"channel_{i}", {})
            channel = MixerChannel(i, self.midi, chan_config)
            self.channels.append(channel)
            self.layout.add_widget(channel)

        right_panel = BoxLayout(orientation='vertical', size_hint_x=0.3)
        self.compressor_btn = MidiCompressorButton(self.midi, self.config_data)
        right_panel.add_widget(self.compressor_btn)

        save_btn = Button(text="💾 Сохранить", size_hint_y=0.2)
        save_btn.bind(on_press=self.save_config)
        right_panel.add_widget(save_btn)

        self.layout.add_widget(right_panel)
        return self.layout

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}

    def save_config(self, instance=None):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config_data, f, indent=2)

if __name__ == '__main__':
    MidiControllerApp().run()
