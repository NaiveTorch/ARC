Getting Started with ARC Open Source on Linux
=============================================

A small set of shared objects can be built which are part of ARC currently.
A fully running system cannot currently be built.

### To Check Out:

1. Run

        git clone --recursive \
               https://chromium.googlesource.com/arc/arc


### Prerequisites for Building:

1. You must be building on Linux and have Ubuntu 12.04 or 14.04.

2. Install depot_tools:
      <http://dev.chromium.org/developers/how-tos/install-depot-tools>

    CAVEAT: depot_tools has an executable called ninja.  You might have an
    Ubuntu package ninja installed on your system, that is not the same thing.

3. Run src/build/install-arc-deps.sh or src/build/install-build-deps.sh to
   make sure your dependencies are up to date.

         $ ./src/build/install-arc-deps.sh    # Ubuntu 12.04

    or

         $ ./src/build/install-build-deps.sh  # Ubuntu 14.04

4. Run the configure script.  Arguments to this script indicate the build
   target and what experimental code you want to be using.  Note that the fewer
   options you pass, the more tested the code you are running.  The configure
   script will be rerun automatically by ninja when it detects a dependency has
   changed.  Also note that configure will download and keep synchronized a
   number of SDKs and test suites that we use in development.

    If you want to build ARC for NaCl (x86-64), use:

         $ ./configure

    If you want to build ARC for NaCl (x86-32), use:

         $ ./configure --target=nacl_i686

    If you want to build ARC for Bare Metal (arm), use:

         $ ./configure --target=bare_metal_arm

### To Build:

    $ ninja


### To Clean:

    $ ninja -t clean


### Resulting Binaries:

Shared objects from this build will be available in out/target/$TARGET/lib.


### Testing a Change:

It is possible to make changes to the code and test them on a Chromebook.
Here are the instructions:

1. Switch your Chromebook into dev mode.
2. Download the App Runtime for Chrome onto the Chromebook by installing an
   ARC app.
3. Synchronize your open source checkout with the version of the App Runtime
   for Chrome your are modifying.  For instance if you are modifying version
   38.4410.120.9 of the ARC Runtime, check out the arc-runtime-38.4410.120.9
   tag in the git repository.
4. Make a change to some code.  For instance, add a message that is printed
   out whenever localtime is called.  Edit localtime.c in mods/android/bionic
   and add the line below to localtime_r function:

     write(1, "#### Here in localtime!!!!\n", 27);

5. Run configure with the architecture appropriate to your Chromebook.  For
   x86-based Chromebooks use -tnx.  For ARM-based Chromebooks use -tba.
6. Run ninja to build your changes.
7. Copy all affected libraries from out/target/nacl_{x86_64,bare_metal_arm}
   to a USB device or cloud storage.  For the example change above, you would
   copy libc.so.
8. Open the shell on your Chromebook and change to the extension directory
   of the App Runtime for Chrome.  The extension ID is shown in the
   chrome:extensions view.  For the given version of the runtime above, the
   directory is Extensions/mfaihdlpglflfgpfjcifdjdjcckigekc/38.4410.120.9_0.
9. Copy the built libraries from our ARC open source checkout to the
   _platform_specific/nacl_{x86_64,bare_metal_arm} directory.
10. Run an app with the new runtime.  You should see the effects of your
    new library.  In the above example you would be able to see the stdout
    output appear in /var/log/ui/ui.LATEST file when the ARC runtime starts.
