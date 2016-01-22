# app defaults
app=send-money
port=8004
browsersync_port=3004
browsersync_ui_port=3034

# include shared Makefile, installing it if necessary
./node_modules/money-to-prisoners-common:
	@echo "The installation process is about to start. It usually takes a while."
	@echo "The only thing that this script doesn't do is set up the API. While"
	@echo "installation is running, head to https://github.com/ministryofjustice/money-to-prisoners-api"
	@echo "to find out how to run it."
	@npm install

%: ./node_modules/money-to-prisoners-common
include node_modules/money-to-prisoners-common/Makefile
