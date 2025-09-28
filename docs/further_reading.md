# **Further Reading**

------------
The cooler I bought originally was the Thermalright "FrozenWarframe" as shown [here ](https://thermalright.com/product/frozen-warframe-240-black-argb/ "here ")

I was gutted when I found out that their software is Windows only and that I had a nice LCD sat on top of the pump on my ryzen7 that showed precisely nothing.  The cooler itself is great, the software support, much less so.

After some weeks, and some thought, I decided to spin up Windows in a VM, pass through the LCD, and use [wireshark](https://www.wireshark.org/ "wireshark") to capture the usb packets and try to reverse engineer something to drive it.

The original sysmon.py was written as a proof of concept to be able to drive the LCD with "something".  All of that initial design has now been converted to c++ , with a python front end gui to make it easy to use.

The current CLcdDriver can load static and dynamic (video) backgrounds and overlay metrics on top.  As Thermalright supply some short (less than 10 seconds) mp4 videos, the driver will pre-load all the frames of any video that is 10 seconds or less in duration.  The vendor supplied videos are all at 24fps.

If you specify a longer video, the driver will switch to "streaming" mode and read each frame, overlay your metrics, and then send it to the lcd. At the end of the video, it will re-start.

Possible video formats are

- mov
- avi
- mp4
- mkv

Frames are automatically resized to the LCD's resolution of 320x240.  You can, if you want, watch something like Terminator 2 on it (yes I have but with no sound obviously!).

### Moving Forwards !!

------------

I'd like to reproduce the theme manager that the original Windows software has, along with the transparency.  At the moment, this driver removes the alpha channel from any images.  It is still pretty versatile though.

Sadly, Thermalright are not interested in supporting any of their lcd's on Linux (I asked them if they would and got a resounding NO) so it's down to the community to do so.

**However**, don't be blaming me if features don't work as expected or you break your LCD.  Use this software at your own risk!!  It works for me, but I can't test the nVidia or Intel metrics as all my kit is AMD.

Suggestions, PR's etc are all welcome although I make no promises that I will implement them, merge them or even read them !!  My time is short, and valuable to me at least! 