import os
import tkinter as tk
import logging
from pathlib import Path

from tilia.ui.common import format_media_time

logger = logging.getLogger(__name__)
from typing import Literal

from tilia.events import Event, subscribe, unsubscribe_from_all
from tilia import events, dirs


class PlayerUI(tk.Frame):
    def __init__(self, parent):
        logger.debug("Creating PlayerUI...")
        super().__init__(parent)

        subscribe(self, Event.PLAYER_MEDIA_TIME_CHANGE, self.on_new_audio_time)
        subscribe(self, Event.PLAYER_MEDIA_LOADED, self.on_media_load)
        subscribe(self, Event.PLAYER_STOPPED, self.on_player_stop)
        subscribe(self, Event.PLAYER_PAUSED, lambda: self.change_playpause_icon("play"))
        subscribe(
            self, Event.PLAYER_UNPAUSED, lambda: self.change_playpause_icon("pause")
        )

        self.media_length_str = "0:00:00"

        # Create player control parent
        self.controls = tk.Frame(self)
        self.controls.pack(side=tk.LEFT, padx=5, pady=5)

        # get player button images
        self.play_btn_img = tk.PhotoImage(
            master=self, file=Path(dirs.img_path, "play15.png")
        )
        self.pause_btn_img = tk.PhotoImage(
            master=self, file=Path(dirs.img_path, "pause15.png")
        )
        self.stop_btn_img = tk.PhotoImage(
            master=self, file=Path(dirs.img_path, "stop15.png")
        )

        # Create player control buttons
        self.play_btn = tk.Button(
            self.controls,
            image=self.play_btn_img,
            borderwidth=0,
            command=lambda: events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE),
            takefocus=False,
        )
        self.stop_btn = tk.Button(
            self.controls,
            image=self.stop_btn_img,
            borderwidth=0,
            command=lambda: events.post(Event.PLAYER_REQUEST_TO_STOP),
            takefocus=False,
        )

        # grid player buttons
        self.play_btn.grid(row=0, column=2, padx=10)
        self.stop_btn.grid(row=0, column=4, padx=10)

        # Create song time indicator
        self.time_label = tk.Label(self, text=f"00:00/00:00")
        self.time_label.pack(side=tk.RIGHT, padx=5, pady=5)

        logger.debug("Created PlayerUI.")

    def __str__(self):
        return f"{self.__class__.__name__}({id(self)})"

    def change_playpause_icon(self, icon_name: Literal["play", "pause"]):

        if icon_name == "play":
            self.play_btn.config(image=self.play_btn_img)
        elif icon_name == "pause":
            self.play_btn.config(image=self.pause_btn_img)
        else:

            raise ValueError(
                f"Unrecognized icon name '{icon_name}' for play/pause icon change."
            )

    def on_new_audio_time(self, audio_time: float) -> None:
        self.time_label.config(
            text=f"{format_media_time(audio_time)}/{self.media_length_str}"
        )

    def on_player_stop(self) -> None:
        self.time_label.config(text=f"0:00:00/{self.media_length_str}")
        self.change_playpause_icon("play")

    def on_player_paused(self):
        self.play_btn.config(image=self.pause_btn_img)

    def on_player_unpaused(self):
        pass

    def on_media_load(self, _1, _2, playback_length: float, _3) -> None:
        self.media_length_str = format_media_time(playback_length)
        self.time_label.config(text=f"0:00:00/{self.media_length_str}")

    def destroy(self):
        tk.Frame.destroy(self)
        unsubscribe_from_all(self)
