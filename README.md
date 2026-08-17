# Calyre

```text                          
                    .%%.                    
                    =%%+                    
              -%#:  .%%.  :*%-              
              -%%%%+ %% =%%%%-              
                 :=%%##%%=:                 
                 :=%%##%%=:                 
              -%%%%+ %% =%%%%-              
              -%#:  .%%.  :*%-              
                    +%%+                    
                    .%%.                    
```

**Calyre** is a programming language designed to be simple, expressive, and easy to experiment with.

This repository contains the reference implementation of Calyre.

## Features

* Simple, readable syntax
* Variables and expressions
* Functions
* Conditional statements
* Loops
* Basic data types
* Explicit type conversion
* Built-in functions
* `.cly` source files
* Command-line interpreter
* No external dependencies required to run the interpreter

## Example

```cly
let name = "World"

print("Hello, " + name + "!")
```

A slightly larger example:

```cly
let name = "Calyre"
let version = 3

print("Welcome to " + name)
print("Version: " + str(version))

if version >= 3 {
    print("This is a modern version of Calyre.")
} else {
    print("This is an older version of Calyre.")
}
```

## Installation

Calyre currently only requires **Python 3**.

### Prebuilt Binary

The easiest way to use Calyre on Windows is to download the latest release from the [Releases](https://github.com/Matt-The-Generico/calyre/releases) page.

Download `calyre.exe` and add its location to your system `PATH` if you want to run Calyre from anywhere.

You can then use:

```powershell
calyre

calyre version

## Usage

Run a Calyre program:

```bash
calyre run program.cly
```

Check a program without running it:

```bash
calyre check program.cly
```

You can also run the interpreter directly through Python if you are working from the source repository.

## File Extension

Calyre source files use the:

```text
.cly
```

extension.

For example:

```text
hello.cly
calculator.cly
game.cly
```

## Types

Calyre supports several basic types, including:

```text
int
float
string
bool
```

Calyre does not automatically convert integers and floating-point numbers between each other.

For example, explicit conversion can be used when necessary:

```cly
let x = 10
let y = float(x)
```

or:

```cly
let x = 10.5
let y = int(x)
```

This keeps type conversions explicit and predictable.

## Testing

The project includes tests for the interpreter and language features.

Run the test suite from the project directory using the project's configured test command.

## Philosophy

Calyre is intended to be a language that is:

**Readable.**
Code should be understandable without requiring excessive syntax.

**Predictable.**
Language behavior should be explicit rather than relying heavily on implicit conversions or surprising rules.

**Experimental.**
Calyre is also a project for exploring programming-language design and interpreter implementation.

## Status

Calyre is currently under active development.

The reference implementation is functional, but the language specification and implementation may continue to evolve.

Syntax and behavior may change between versions.

## Contributing

Contributions, bug reports, suggestions, and experiments are welcome.

If you find a bug, please open an issue describing:

1. What you expected to happen
2. What actually happened
3. The Calyre code that reproduces the problem
4. Any relevant error messages

For larger changes, opening an issue first is recommended so the proposed change can be discussed.

## License

See the repository's license information for the terms under which Calyre may be used, modified, and distributed.

---

Made by uchoa

**Calyre**

*make stuff now.*
