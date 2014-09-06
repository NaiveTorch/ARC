;; Copyright (c) 2012 The Chromium Authors. All rights reserved.
;; Use of this source code is governed by a BSD-style license that can be
;; found in the LICENSE file.

;; Set up flymake for use with ARC code.  Heavily borrows from
;; flymake-chromium.el.

(require 'flymake)

(defcustom inc-flymake-ninja-build-file "build.ninja"
  "Relative path from ARC's top level directory to the
  build.ninja file to use.")

(defcustom inc-flymake-ninja-executable "ninja"
  "Ninja executable location; either in $PATH or explicitly given.")

(defun inc-flymake-absbufferpath ()
  "Return the absolute path to the current buffer, or nil if the
  current buffer has no path."
  (when buffer-file-truename
      (expand-file-name buffer-file-truename)))

(defun inc-flymake-arc-dir ()
  "Return ARC's top level directory, or nil on failure."
  (let ((srcdir (locate-dominating-file
                 (inc-flymake-absbufferpath) inc-flymake-ninja-build-file)))
    (when srcdir (expand-file-name srcdir))))

(defun inc-flymake-string-prefix-p (prefix str)
  "Return non-nil if PREFIX is a prefix of STR (23.2 has string-prefix-p but
  that's case insensitive and also 23.1 doesn't have it)."
  (string= prefix (substring str 0 (length prefix))))

(defun inc-flymake-as-staging (path trim)
  "Return the staging path for a given source path."
  (if trim
      (concat "out/staging/" (replace-regexp-in-string "^[^/]+/" "" path))
    (concat "out/staging/" path)))

(defun inc-flymake-current-file-name ()
  "Return the relative path from ARC's top level directory to the
  build target for the current buffer or nil."
  (when (and (inc-flymake-arc-dir)
             (inc-flymake-string-prefix-p
              (inc-flymake-arc-dir) (inc-flymake-absbufferpath)))
    (let* ((relative-path (substring (inc-flymake-absbufferpath)
                                    (length (inc-flymake-arc-dir))))
           (staging-path-1 (inc-flymake-as-staging relative-path t))
           (staging-path-2 (inc-flymake-as-staging relative-path nil)))
      (or (and (file-exists-p (concat (inc-flymake-arc-dir) staging-path-1))
               staging-path-1)
          (and (file-exists-p (concat (inc-flymake-arc-dir) staging-path-2))
               staging-path-2)))))


(defun inc-flymake-from-build-to-src-root ()
  "Return a path fragment for getting from the build.ninja file to src/."
  (replace-regexp-in-string
   "[^/]+" ".."

   (substring
    (file-name-directory
     (file-truename (or (and (inc-flymake-string-prefix-p
                              "/" inc-flymake-ninja-build-file)
                             inc-flymake-ninja-build-file)
                        (concat (inc-flymake-arc-dir)
                                inc-flymake-ninja-build-file))))
    (length (inc-flymake-arc-dir)))))

(defun inc-flymake-getfname (file-name-from-error-message)
  "Strip cruft from the passed-in filename to help flymake find the real file."
  (file-name-nondirectory file-name-from-error-message))

(defun inc-flymake-ninja-command-line ()
  "Return the command-line for running ninja, as a list of strings, or nil if
  we're not during a save"
  (unless (buffer-modified-p)
    (list inc-flymake-ninja-executable
          (list "-C"
                (concat (inc-flymake-arc-dir)
                        (file-name-directory inc-flymake-ninja-build-file))
                (concat (inc-flymake-from-build-to-src-root)
                        (inc-flymake-current-file-name) "^")))))

(defun inc-flymake-kick-off-check-after-save ()
  "Kick off a syntax check after file save, if flymake-mode is on."
  (when flymake-mode (flymake-start-syntax-check)))

(defadvice next-error (around inc-flymake-next-error activate)
  "If flymake has something to say, let it say it; otherwise
   revert to normal next-error behavior."
  (if (not flymake-err-info)
      (condition-case msg
          ad-do-it
        (error (message "%s" (prin1-to-string msg))))
    (flymake-goto-next-error)
    ;; copy/pasted from flymake-display-err-menu-for-current-line because I
    ;; couldn't find a way to have it tell me what the relevant error for this
    ;; line was in a single call:
    (let* ((line-no (flymake-current-line-no))
           (line-err-info-list
            (nth 0 (flymake-find-err-info flymake-err-info line-no)))
           (menu-data (flymake-make-err-menu-data line-no line-err-info-list)))
      (prin1 (car (car (car (cdr menu-data)))) t))))

(defun inc-flymake-find-file ()
  "Enable flymake, but only if it makes sense, and immediately
  disable timer-based execution."
  (when (and (not flymake-mode)
             (not buffer-read-only)
             (inc-flymake-current-file-name))
    ;; Since flymake-allowed-file-name-masks requires static regexps to match
    ;; against, can't use inc-flymake-arc-dir here.  Instead we add a
    ;; generic regexp, but only to a buffer-local version of the variable.
    (set (make-local-variable 'flymake-allowed-file-name-masks)
         (list (list "\\.c\\(\\|c\\|pp\\)"
                     'inc-flymake-ninja-command-line
                     'ignore
                     'inc-flymake-getfname)))
    (flymake-find-file-hook)
    (if flymake-mode
        (cancel-timer flymake-timer)
      (kill-local-variable 'flymake-allowed-file-name-masks))))

(add-hook 'find-file-hook 'inc-flymake-find-file 'append)
(add-hook 'after-save-hook 'inc-flymake-kick-off-check-after-save)

;; Show flymake infrastructure ERRORs in hopes of fixing them.  Set to 3 for
;; DEBUG-level output from flymake.el.
(setq flymake-log-level 0)

(provide 'flymake-arc)
