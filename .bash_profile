export JAVA_8_HOME=$(/usr/libexec/java_home -v1.8.0_232)
export JAVA_11_HOME=$(/usr/libexec/java_home -v11.0.8)
export JAVA_14_HOME=$(/usr/libexec/java_home -v14.0.2)

alias java8='export JAVA_HOME=$JAVA_8_HOME'
alias java11='export JAVA_HOME=$JAVA_11_HOME'
alias java14='export JAVA_HOME=$JAVA_14_HOME'

#default java8
export JAVA_HOME=$JAVA_8_HOME

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
