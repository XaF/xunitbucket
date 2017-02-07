all: build

build:
	@docker build --tag=bhvrops/xunitbucket .

