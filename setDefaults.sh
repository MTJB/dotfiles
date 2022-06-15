#!/bin/bash

# Change default screenshot dir, move to trash automatically
mkdir -p /Users/mark/Pictures/Screenshots;
defaults write com.apple.screencapture location /Users/mark/Pictures/Screenshots
cp automation/com.mark.clean-screenshots-dir.plist ~/Library/LaunchAgents
sudo chown root:wheel ~/Library/LaunchAgents/com.mark.clean-screenshots-dir.plist # After Big Sur, need to transfer ownershipto root
sudo chmod 600 ~/Library/LaunchAgents/com.mark.clean-screenshots-dir.plist
sudo launchctl load -w ~/Library/LaunchAgents/com.mark.clean-screenshots-dir.plist
