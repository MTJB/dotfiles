#!/bin/bash

# Change default screenshot dir, move to trash automatically
mkdir -p /Users/mark/Pictures/Screenshots;
defaults write com.apple.screencapture location /Users/mark/Pictures/Screenshots
cp automation/com.mark.clean-screenshots-dir.plist ~/Library/LaunchAgents
launchctl load ~/Library/LaunchAgents/com.mark.clean-screenshots-dir.plist
