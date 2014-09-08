#include <arpa/inet.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/ip.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

#define DPRINTF(errlvl, domain, fmtstr, ...) \
    fprintf(stderr, fmtstr, ##__VA_ARGS__)

int
getsysaddr(char * buf, int len)
{
	int i;
	int s = socket(PF_INET, SOCK_STREAM, 0);
	struct sockaddr_in addr;
	struct ifreq ifr;
	int ret = -1;

	for (i=1; i > 0; i++)
	{
		ifr.ifr_ifindex = i;
		if( ioctl(s, SIOCGIFNAME, &ifr) < 0 )
			break;
		if(ioctl(s, SIOCGIFADDR, &ifr, sizeof(struct ifreq)) < 0)
			continue;
		memcpy(&addr, &ifr.ifr_addr, sizeof(addr));
		if(strncmp(inet_ntoa(addr.sin_addr), "127.", 4) == 0)
			continue;
		if(!inet_ntop(AF_INET, &addr.sin_addr, buf, len))
		{
			DPRINTF(E_ERROR, L_GENERAL, "inet_ntop(): %s\n", strerror(errno));
			close(s);
			break;
		}
		ret = 0;
		break;
	}
	close(s);

	return(ret);
}

int main()
{
    char name[INET_ADDRSTRLEN] = {};
    getsysaddr(name, sizeof(name));
    printf("%s\n", name);
    return 0;
}
