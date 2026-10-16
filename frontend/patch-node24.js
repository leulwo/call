const fs = require("fs");

function makeEinval(path) {
  const einval = new Error(`EINVAL: invalid argument, readlink '${path}'`);
  einval.code = "EINVAL";
  einval.errno = -4071;
  einval.syscall = "readlink";
  einval.path = String(path);
  return einval;
}

// 1. Sync
const origReadlinkSync = fs.readlinkSync;
fs.readlinkSync = function (path, options) {
  try {
    return origReadlinkSync.call(fs, path, options);
  } catch (err) {
    if (err && (err.code === "EISDIR" || err.errno === -4068)) {
      throw makeEinval(path);
    }
    throw err;
  }
};

// 2. Callback
const origReadlink = fs.readlink;
fs.readlink = function (path, ...args) {
  const cb = args[args.length - 1];
  if (typeof cb === "function") {
    const wrappedCb = (err, linkString) => {
      if (err && (err.code === "EISDIR" || err.errno === -4068)) {
        return cb(makeEinval(path));
      }
      return cb(err, linkString);
    };
    args[args.length - 1] = wrappedCb;
  }
  return origReadlink.call(fs, path, ...args);
};

// 3. Promises
if (fs.promises && fs.promises.readlink) {
  const origPromisesReadlink = fs.promises.readlink;
  fs.promises.readlink = async function (path, options) {
    try {
      return await origPromisesReadlink.call(fs.promises, path, options);
    } catch (err) {
      if (err && (err.code === "EISDIR" || err.errno === -4068)) {
        throw makeEinval(path);
      }
      throw err;
    }
  };
}
