package main

import (
	"fmt"
	"runtime"
)

var version = "development"

func main() {
	fmt.Printf("releaseway-native-fixture %s %s/%s %s\n", version, runtime.GOOS, runtime.GOARCH, runtime.Version())
}
