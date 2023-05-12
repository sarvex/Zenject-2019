
import os
import re
import sys
from mtm.ioc.Inject import Inject
import mtm.util.Util as Util
from mtm.log.Logger import LogType
import shutil

from mtm.util.Assert import *
import mtm.log.ColorConsole as ColorConsole

class AnsiiCodes:
    BLACK = "\033[1;30m"
    DARKBLACK = "\033[0;30m"
    RED = "\033[1;31m"
    DARKRED = "\033[0;31m"
    GREEN = "\033[1;32m"
    DARKGREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    DARKYELLOW = "\033[0;33m"
    BLUE = "\033[1;34m"
    DARKBLUE = "\033[0;34m"
    MAGENTA = "\033[1;35m"
    DARKMAGENTA = "\033[0;35m"
    CYAN = "\033[1;36m"
    DARKCYAN = "\033[0;36m"
    WHITE = "\033[1;37m"
    DARKWHITE = "\033[0;37m"
    END = "\033[0;0m"

class LogMap:
    def __init__(self, regex, sub):
        self.regex = regex
        self.sub = sub

class LogStreamConsole:
    _log = Inject('Logger')
    _sys = Inject('SystemHelper')
    _varManager = Inject('VarManager')
    _config = Inject('Config')

    def __init__(self, verbose, veryVerbose):
        self._verbose = verbose
        self._veryVerbose = veryVerbose

        self.headingPatterns = self._getPatterns('HeadingPatterns')
        self.headingMaps = self._getPatternMaps('HeadingPatternMaps')

        self.goodPatterns = self._getPatterns('GoodPatterns')
        self.goodMaps = self._getPatternMaps('GoodPatternMaps')

        self.infoPatterns = self._getPatterns('InfoPatterns')
        self.infoMaps = self._getPatternMaps('InfoPatternMaps')

        self.errorPatterns = self._getPatterns('ErrorPatterns')
        self.errorMaps = self._getPatternMaps('ErrorPatternMaps')

        self.warningPatterns = self._getPatterns('WarningPatterns')
        self.warningMaps = self._getPatternMaps('WarningPatternMaps')
        self.warningPatternsIgnore = self._getPatterns('WarningPatternsIgnore')

        self.debugPatterns = self._getPatterns('DebugPatterns')
        self.debugMaps = self._getPatternMaps('DebugPatternMaps')

        self._useColors = self._config.tryGetBool(False, 'Console', 'UseColors')

        self._fileStream = None
        if self._config.tryGetBool(False, 'Console', 'OutputToFilteredLog'):
            self._fileStream = self._getFileStream()

        if self._useColors:
            self._initColors()

    def _initColors(self):
        self._defaultColors = ColorConsole.get_text_attr()
        self._defaultBg = self._defaultColors & 0x0070
        self._defaultFg = self._defaultColors & 0x0007

    def log(self, logType, message):

        logType, message = self.classifyMessage(logType, message)

        if logType is not None:
            if logType in [LogType.HeadingFailed, LogType.Error]:
                self._output(logType, message, sys.stderr, self._useColors)
            else:
                self._output(logType, message, sys.stdout, self._useColors)

            if self._fileStream:
                self._output(logType, message, self._fileStream, False)

    def _getFileStream(self):

        primaryPath = self._varManager.expand('[LogFilteredPath]')

        if not primaryPath:
            raise Exception("Could not find path for log file")

        previousPath = None
        if self._varManager.hasKey('LogFilteredPreviousPath'):
            previousPath = self._varManager.expand('[LogFilteredPreviousPath]')

        # Keep one old build log
        if os.path.isfile(primaryPath) and previousPath:
            shutil.copy2(primaryPath, previousPath)

        return open(primaryPath, 'w', encoding='utf-8', errors='ignore')

    def _output(self, logType, message, stream, useColors):

        stream.write('\n')

        if self._log.hasHeading and logType != LogType.Heading and logType != LogType.HeadingSucceeded and logType != LogType.HeadingFailed:
            stream.write('  ')

        if not useColors or logType == LogType.Info:
            stream.write(message)
            stream.flush()
        else:
            ColorConsole.set_text_attr(self._getColorAttrs(logType))
            stream.write(message)
            stream.flush()
            ColorConsole.set_text_attr(self._defaultColors)

    def _getColorAttrs(self, logType):
        if logType in [LogType.Heading, LogType.HeadingSucceeded]:
            return ColorConsole.FOREGROUND_CYAN | self._defaultBg | ColorConsole.FOREGROUND_INTENSITY

        if logType == LogType.Good:
            return ColorConsole.FOREGROUND_GREEN | self._defaultBg | ColorConsole.FOREGROUND_INTENSITY

        if logType == LogType.Warn:
            return ColorConsole.FOREGROUND_YELLOW | self._defaultBg | ColorConsole.FOREGROUND_INTENSITY

        if logType in [LogType.Error, LogType.HeadingFailed]:
            return ColorConsole.FOREGROUND_RED | self._defaultBg | ColorConsole.FOREGROUND_INTENSITY

        if logType == LogType.Debug:
            return ColorConsole.FOREGROUND_BLACK | self._defaultBg | ColorConsole.FOREGROUND_INTENSITY

        assertThat(False, 'Unrecognized log type "{0}"'.format(logType))

    def _getPatternMaps(self, settingName):
        maps = self._config.tryGetDictionary({}, 'Console', settingName)

        result = []
        for key, value in maps.items():
            regex = re.compile(key)
            logMap = LogMap(regex, value)
            result.append(logMap)

        return result

    def _getPatterns(self, settingName):
        patternStrings = self._config.tryGetList([], 'Console', settingName)

        return [re.compile(f'.*{pattern}.*') for pattern in patternStrings]

    def tryMatchPattern(self, message, maps, patterns):
        for logMap in maps:
            if logMap.regex.match(message):
                return logMap.regex.sub(logMap.sub, message)

        for pattern in patterns:
            if match := pattern.match(message):
                groups = match.groups()

                return groups[0] if len(groups) > 0 else message
        return None

    def classifyMessage(self, logType, message):

        if logType in [
            LogType.Info,
            LogType.Heading,
            LogType.HeadingFailed,
            LogType.HeadingSucceeded,
            LogType.Good,
            LogType.Warn,
            LogType.Error,
        ]:
            return logType, message

        if parsedMessage := self.tryMatchPattern(
            message, self.errorMaps, self.errorPatterns
        ):
            return LogType.Error, parsedMessage

        if not any(p.match(message) for p in self.warningPatternsIgnore):
            if parsedMessage := self.tryMatchPattern(
                message, self.warningMaps, self.warningPatterns
            ):
                return LogType.Warn, parsedMessage

        if parsedMessage := self.tryMatchPattern(
            message, self.headingMaps, self.headingPatterns
        ):
            return LogType.Heading, parsedMessage

        if parsedMessage := self.tryMatchPattern(
            message, self.goodMaps, self.goodPatterns
        ):
            return LogType.Good, parsedMessage

        if parsedMessage := self.tryMatchPattern(
            message, self.infoMaps, self.infoPatterns
        ):
            return LogType.Info, parsedMessage

        if self._verbose:
            if parsedMessage := self.tryMatchPattern(
                message, self.debugMaps, self.debugPatterns
            ):
                return LogType.Debug, parsedMessage

        return (LogType.Debug, message) if self._veryVerbose else (None, message)

