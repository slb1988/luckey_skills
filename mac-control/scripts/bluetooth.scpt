-- 用法: osascript bluetooth.scpt on|off
-- 幂等; 关闭时自动处理「确定要关闭蓝牙吗?」确认框; 返回 already/now=0|1
on run argv
	set target to item 1 of argv
	do shell script "open 'x-apple.systempreferences:com.apple.Bluetooth'"
	delay 1.5
	tell application "System Events"
		tell process "System Settings"
			set frontmost to true
			delay 0.8
			set w to window "蓝牙"
			set sw to checkbox 1 of group 1 of scroll area 1 of group 1 of group 2 of splitter group 1 of group 1 of w
			set want to 0
			if target is "on" then set want to 1
			if (value of sw as integer) is want then return "already " & target
			click sw
			if want is 0 then
				repeat 10 times
					delay 0.5
					if exists sheet 1 of w then
						click button 2 of sheet 1 of w
						delay 1
						exit repeat
					end if
				end repeat
			else
				delay 1
			end if
			return "now=" & ((value of sw) as integer)
		end tell
	end tell
end run
