from typing import Iterator

from .build import BuildManager
from ..core.bug import Bug
from ..util import print_task_start, print_task_end


class BugManager(object):
    """
    Used to access and manage all bugs registered with a local BugZoo
    installation.
    """
    class BugIterator(object):
        def __init__(self, datasets):
            self.__datasets = [d for d in datasets]
            self.__bugs = []

        def __next__(self):
            if not self.__bugs:
                if not self.__datasets:
                    raise StopIteration
                src = self.__datasets.pop()
                self.__bugs += src.bugs
                return self.__next__()
            return self.__bugs.pop()

    def __init__(self,
                 installation: 'BugZoo',
                 manager_build: BuildManager):
        self.__installation = installation
        self.__manager_build = manager_build

    def __getitem__(self, name: str) -> Bug:
        for src in self.__installation.datasets:
            if src.contains(name):
                return src[name]
        raise IndexError('bug not found: {}'.format(name))

    def __iter__(self) -> Iterator[Bug]:
        return BugManager.BugIterator(self.__installation.datasets)

    def is_installed(self, bug: Bug) -> bool:
        """
        Determines whether or not the Docker image for a given bug has been
        installed onto this server.

        See: `BuildManager.is_installed`
        """
        return self.__manager_build.is_installed(bug.build_instructions)

    def build(self,
              bug: Bug,
              force: bool = False,
              quiet: bool = False
              ) -> None:
        """
        Builds the Docker image associated with a given bug.

        See: `BuildManager.build`
        """
        self.__manager_build.build(bug.build_instructions,
                                   force=force,
                                   quiet=quiet)

    def uninstall(self,
                  bug: Bug,
                  force: bool = False,
                  noprune: bool = False
                  ) -> None:
        """
        Uninstalls all Docker images associated with this bug.

        See: `BuildManager.uninstall`
        """
        self.__manager_build.uninstall(bug.build_instructions,
                                       force=force,
                                       noprune=noprune)

    def download(self,
                 bug: Bug,
                 force=False) -> bool:
        """
        Attempts to download the Docker image for a given bug from
        `DockerHub <https://hub.docker.com>`_. If the force parameter is set to
        True, any existing image will be overwritten.

        Returns:
            `True` if successfully downloaded, else `False`.
        """
        return self.__manager_build.download(bug.build_instructions,
                                             force=force)

    def upload(self, bug: Bug) -> bool:
        """
        Attempts to upload the Docker image for a given bug to
        `DockerHub <https://hub.docker.com>`_.
        """
        return self.__manager_build.upload(bug.build_instructions)

    def validate(self, bug: Bug, verbose: bool = True) -> bool:
        """
        Checks that a given bug successfully builds, and that it produces an
        expected set of test suite outcomes.

        Parameters:
            verbose: toggles verbosity of output. If set to `True`, the
                outcomes of each test will be printed to the standard output.

        Returns:
            `True` if bug behaves as expected, else `False`.
        """
        # attempt to rebuild -- don't worry, Docker's layer caching prevents us
        # from actually having to rebuild everything from scratch :-)
        try:
            self.build(bug, force=True, quiet=True)
        except docker.errors.BuildError:
            print("failed to build bug: {}".format(self.identifier))
            return False

        # provision a container
        validated = True
        try:
            c = None
            c = bug.provision()

            # ensure we can compile the bug
            # TODO: check compilation status!
            print_task_start('Compiling')
            c.compile()
            print_task_end('Compiling', 'OK')

            if isinstance(self.harness, bugzoo.testing.GenProgTestSuite):

                for t in self.harness.passing:
                    task = 'Running test: {}'.format(t.identifier)
                    print_task_start(task)

                    outcome = c.execute(t)
                    if not outcome.passed:
                        validated = False
                        print_task_end(task, 'UNEXPECTED: FAIL')
                        response = textwrap.indent(outcome.response.output, ' ' * 4)
                        print('\n' + response)
                    else:
                        print_task_end(task, 'OK')

                for t in self.harness.failing:
                    task = 'Running test: {}'.format(t.identifier)
                    print_task_start(task)

                    outcome = c.execute(t)
                    if outcome.passed:
                        validated = False
                        print_task_end(task, 'UNEXPECTED: PASS')
                        response = textwrap.indent(outcome.response.output, ' ' * 4)
                        print('\n' + response)
                    else:
                        print_task_end(task, 'OK')

        # ensure that the container is destroyed!
        finally:
            if c:
                c.destroy()

        return validated